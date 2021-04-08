import copy
import time
import numpy as np
import math

#functions related to QM/MM
import ash
import module_coords
from functions_general import BC,blankline,listdiff,print_time_rel,printdebug
import settings_ash

#QM/MM theory object.
#Required at init: qm_theory and qmatoms. Fragment not. Can come later
#TODO NOTE: If we add init arguments, remember to update Numfreq QMMM option as it depends on the keywords
class QMMMTheory:
    def __init__(self, qm_theory=None, qmatoms=None, fragment=None, mm_theory=None , charges=None,
                 embedding="Elstat", printlevel=2, nprocs=1, actatoms=None, frozenatoms=None, excludeboundaryatomlist=None,
                 unusualboundary=False):

        print(BC.WARNING,BC.BOLD,"------------Defining QM/MM object-------------", BC.END)

        #Linkatoms False by default. Later checked.
        self.linkatoms=False

        #If fragment object has been defined
        #This probably needs to be always true
        if fragment is not None:
            self.fragment=fragment
            self.coords=fragment.coords
            self.elems=fragment.elems
            self.connectivity=fragment.connectivity

            # Region definitions
            self.allatoms=list(range(0,len(self.elems)))
            print("All atoms in fragment:", len(self.allatoms))
            #Sorting qmatoms list
            self.qmatoms = sorted(qmatoms)
            self.mmatoms=listdiff(self.allatoms,self.qmatoms)

            # FROZEN AND ACTIVE ATOMS
            if actatoms is None and frozenatoms is None:
                print("Actatoms/frozenatoms list not passed to QM/MM object. Will do all frozen interactions in MM (expensive).")
                print("All {} atoms active, no atoms frozen".format(len(self.allatoms)))
                self.actatoms=self.allatoms
                self.frozenatoms=[]
            elif actatoms is not None and frozenatoms is None:
                print("Actatoms list passed to QM/MM object. Will skip all frozen interactions in MM.")
                #Sorting actatoms list
                self.actatoms = sorted(actatoms)
                self.frozenatoms = listdiff(self.allatoms, self.actatoms)
                print("{} active atoms, {} frozen atoms".format(len(self.actatoms), len(self.frozenatoms)))
            elif frozenatoms is not None and actatoms is None:
                print("Frozenatoms list passed to QM/MM object. Will skip all frozen interactions in MM.")
                self.frozenatoms = sorted(frozenatoms)
                self.actatoms = listdiff(self.allatoms, self.frozenatoms)
                print("{} active atoms, {} frozen atoms".format(len(self.actatoms), len(self.frozenatoms)))
            else:
                print("active_atoms and frozen_atoms can not be both defined")
                exit(1)
            
            #print("List of all atoms:", self.allatoms)
            print("QM region ({} atoms): {}".format(len(self.qmatoms),self.qmatoms))
            print("MM region ({} atoms)".format(len(self.mmatoms)))
            #print("MM region", self.mmatoms)
            blankline()

            #TO delete
            #List of QM and MM labels
            #self.hybridatomlabels=[]
            #for i in self.allatoms:
            #    if i in self.qmatoms:
            #        self.hybridatomlabels.append('QM')
            #   elif i in self.mmatoms:
            #        self.hybridatomlabels.append('MM')
        else:
            print("Fragment has not been defined for QM/MM. Exiting")
            exit(1)

        #Flag to check whether QMCharges have been zeroed in self.charges_qmregionzeroed list
        self.QMChargesZeroed=False

        #Theory level definitions
        self.printlevel=printlevel
        print("self.printlevel: ", self.printlevel)
        self.qm_theory=qm_theory
        self.qm_theory_name = self.qm_theory.__class__.__name__
        
        #Setting QM/MM qmatoms in QMtheory also (used for Spin-flipping currently)
        self.qm_theory.qmatoms=self.qmatoms
        
        self.mm_theory=mm_theory
        self.mm_theory_name = self.mm_theory.__class__.__name__
        if self.mm_theory_name == "str":
            self.mm_theory_name="None"
        print("QM-theory:", self.qm_theory_name)
        print("MM-theory:", self.mm_theory_name)
        
        #Setting nprocs of object.
        #This will be when calling QMtheory and probably MMtheory
        
        #nproc-setting in QMMMTheory takes precedent
        if nprocs != 1:
            self.nprocs=nprocs
        #If QMtheory nprocs was set (and QMMMTHeory not)
        elif self.qm_theory.nprocs != 1:
            self.nprocs=self.qm_theory.nprocs
        #Default 1 proc
        else:
            self.nprocs=1
        print("QM/MM object selected to use {} cores".format(self.nprocs))

        #Embedding type: mechanical, electrostatic etc.
        self.embedding=embedding
        print("Embedding:", self.embedding)

        #if atomcharges are not passed to QMMMTheory object, get them from MMtheory (that should have been defined then)
        if charges is None:
            print("No atomcharges list passed to QMMMTheory object")
            self.charges=[]
            if self.mm_theory_name == "OpenMMTheory":
                print("Getting system charges from OpenMM object")
                #Todo: Call getatomcharges directly or should that have been called from within openmm object at init ?
                #self.charges = mm_theory.getatomcharges()
                self.charges = mm_theory.charges
            elif self.mm_theory_name == "NonBondedTheory":
                print("Getting system charges from NonBondedTheory object")
                #Todo: normalize charges vs atom_charges
                self.charges=mm_theory.atom_charges
                        
            else:
                print("Unrecognized MM theory for QMMMTheory")
                exit(1)
        else:
            self.charges=charges
        
        if len(self.charges) == 0:
            print("No charges present in QM/MM object. Exiting...")
            exit()
        
        
        #CHARGES DEFINED FOR OBJECT:
        #Self.charges are original charges that are defined above (on input, from OpenMM or from NonBondedTheory)
        #self.charges_qmregionzeroed is self.charges but with 0-value for QM-atoms
        #self.pointcharges are pointcharges that the QM-code will see (dipole-charges, no zero-valued charges etc)
        #Length of self.charges: system size
        #Length of self.charges_qmregionzeroed: system size
        #Length of self.pointcharges: unknown. does not contain zero-valued charges (e.g. QM-atoms etc.), contains dipole-charges 
        
        #self.charges_qmregionzeroed will have QM-charges zeroed (but not removed)
        self.charges_qmregionzeroed = []
        
        #Self.pointcharges are pointcharges that the QM-program will see (but not the MM program)
        # They have QM-atoms zeroed, zero-charges removed, dipole-charges added etc.
        #Defined later
        self.pointcharges = []

        #If MM THEORY (not just pointcharges)
        if mm_theory is not None:
            #Add possible exception for QM-QM atoms here.
            #Maybe easier to just just set charges to 0. LJ for QM-QM still needs to be done by MM code
            if self.mm_theory_name == "OpenMMTheory":
                print("Now adding exceptions for frozen atoms")
                if len(self.frozenatoms) > 0:
                    print("Here adding exceptions for OpenMM")
                    print("Frozen-atom exceptions currently inactive...")
                    #print("Num frozen atoms: ", len(self.frozenatoms))
                    #Disabling for now, since so bloody slow. Need to speed up
                    #mm_theory.addexceptions(self.frozenatoms)


            #Check if we need linkatoms by getting boundary atoms dict:
            blankline()
            self.boundaryatoms = module_coords.get_boundary_atoms(self.qmatoms, self.coords, self.elems, settings_ash.settings_dict["scale"], 
                settings_ash.settings_dict["tol"], excludeboundaryatomlist=excludeboundaryatomlist, unusualboundary=unusualboundary)
            
            if len(self.boundaryatoms) >0:
                print("Found covalent QM-MM boundary. Linkatoms option set to True")
                print("Boundaryatoms (QM:MM pairs):", self.boundaryatoms)
                self.linkatoms=True
                
                #Get MM boundary information. Stored as self.MMboundarydict
                self.get_MMboundary()
            else:
                print("No covalent QM-MM boundary. Linkatoms option set to False")
                self.linkatoms=False
            

            if self.embedding=="Elstat":
                
                #Remove bonded interactions in MM part. Only in OpenMM. Assuming they were never defined in NonbondedTHeory
                
                if self.mm_theory_name == "OpenMMTheory":
                    print("Removing bonded terms for QM-region in MMtheory")
                    self.mm_theory.modify_bonded_forces(self.qmatoms)

                    #NOTE: Temporary. Exceptions for nonbonded QM atoms. Will ignore QM-QM Coulomb and LJ interactions. Coulomb interactions are also set to zero elsewhere.
                    print("Removing nonbonded terms for QM-region in MMtheory")
                    self.mm_theory.addexceptions(self.qmatoms)
                
                #Change charges
                # Keeping self.charges as originally defined.
                #Setting QM charges to 0 since electrostatic embedding
                #and Charge-shift QM-MM boundary
                
                #Zero QM charges
                #TODO: DO here or inside run instead?? Needed for MM code.
                self.ZeroQMCharges() #Modifies self.charges_qmregionzeroed
                print("length of self.charges_qmregionzeroed :", len(self.charges_qmregionzeroed))
                
                # Todo: make sure this works for OpenMM and for NonBondedTheory
                # Updating charges in MM object. Using charges that have been zeroed for QM (no other modifications)
                #Updated...
                self.mm_theory.update_charges(self.qmatoms,[0.0 for i in self.qmatoms])
                
                
                print("Charges of QM atoms set to 0 (since Electrostatic Embedding):")
                if self.printlevel > 3:
                    for i in self.allatoms:
                        if i in self.qmatoms:
                            print("QM atom {} ({}) charge: {}".format(i, self.elems[i], self.charges_qmregionzeroed[i]))
                        else:
                            print("MM atom {} ({}) charge: {}".format(i, self.elems[i], self.charges_qmregionzeroed[i]))
                blankline()
        else:
            #Case: No actual MM theory but we still want to zero charges for QM elstate embedding calculation
            #TODO: Remove option for no MM theory or keep this ??
            self.ZeroQMCharges() #Modifies self.charges_qmregionzeroed
            print("length of self.charges_qmregionzeroed :", len(self.charges_qmregionzeroed))

    #From QM1:MM1 boundary dict, get MM1:MMx boundary dict (atoms connected to MM1)
    def get_MMboundary(self):
        # if boundarydict is not empty we need to zero MM1 charge and distribute charge from MM1 atom to MM2,MM3,MM4
        #Creating dictionary for each MM1 atom and its connected atoms: MM2-4
        self.MMboundarydict={}
        for (QM1atom,MM1atom) in self.boundaryatoms.items():
            connatoms = module_coords.get_connected_atoms(self.coords, self.elems, settings_ash.settings_dict["scale"], settings_ash.settings_dict["tol"], MM1atom)
            #Deleting QM-atom from connatoms list
            connatoms.remove(QM1atom)
            self.MMboundarydict[MM1atom] = connatoms
        print("")
        print("MM boundary (MM1:MMx pairs):", self.MMboundarydict)
                
    # Set QMcharges to Zero and shift charges at boundary
    #TODO: Add both L2 scheme (delete whole charge-group of M1) and charge-shifting scheme (shift charges to Mx atoms and add dipoles for each Mx atom)
    
    def ZeroQMCharges(self):
        print("Setting QM charges to Zero")
        #Looping over charges and setting QM atoms to zero
        #1. Copy charges to charges_qmregionzeroed
        self.charges_qmregionzeroed=copy.copy(self.charges)
        #2. change charge for QM-atom
        for i, c in enumerate(self.charges_qmregionzeroed):
            #Setting QMatom charge to 0
            if i in self.qmatoms:
                self.charges_qmregionzeroed[i] = 0.0
        #3. Flag that this has been done
        self.QMChargesZeroed = True
    def ShiftMMCharges(self):
        print("Shifting MM charges at QM-MM boundary.")
        print("len self.charges_qmregionzeroed: ", len(self.charges_qmregionzeroed))
        print("len self.charges: ", len(self.charges))
        
        #Create self.pointcharges list
        self.pointcharges=copy.copy(self.charges_qmregionzeroed)
        
        #Looping over charges and setting QM/MM1 atoms to zero and shifting charge to neighbouring atoms
        for i, c in enumerate(self.pointcharges):

            #If index corresponds to MMatom at boundary, set charge to 0 (charge-shifting
            if i in self.MMboundarydict.keys():
                MM1charge = self.charges[i]
                #print("MM1atom charge: ", MM1charge)
                self.pointcharges[i] = 0.0
                #MM1 charge fraction to be divided onto the other MM atoms
                MM1charge_fract = MM1charge / len(self.MMboundarydict[i])
                #print("MM1charge_fract :", MM1charge_fract)

                #TODO: Should charges be updated for MM program also ?
                #Putting the fractional charge on each MM2 atom
                for MMx in self.MMboundarydict[i]:
                    #print("MMx : ", MMx)
                    #print("Old charge : ", self.charges_qmregionzeroed[MMx])
                    self.pointcharges[MMx] += MM1charge_fract
                    #print("New charge : ", self.charges_qmregionzeroed[MMx])
                    #exit()
                
    #Create dipole charge (twice) for each MM2 atom that gets fraction of MM1 charge
    def get_dipole_charge(self,delq,direction,mm1index,mm2index):
        #Distance between MM1 and MM2
        MM_distance = module_coords.distance_between_atoms(fragment=self.fragment, atom1=mm1index, atom2=mm2index)
        #Coordinates
        mm1coords=np.array(self.fragment.coords[mm1index])
        mm2coords=np.array(self.fragment.coords[mm2index])
        
        SHIFT=0.15
        #Normalize vector
        def vnorm(p1):
            r = math.sqrt((p1[0]*p1[0])+(p1[1]*p1[1])+(p1[2]*p1[2]))
            v1=np.array([p1[0] / r, p1[1] / r, p1[2] /r])
            return v1
        diffvector=mm2coords-mm1coords
        normdiffvector=vnorm(diffvector)
        
        #Dipole
        d = delq*2.5
        #Charge (abs value)
        q0 = 0.5 * d / SHIFT
        #print("q0 : ", q0)
        #Actual shift
        #print("direction : ", direction)
        shift = direction * SHIFT * ( MM_distance / 2.5 )
        #print("shift : ", shift)
        #Position
        #print("normdiffvector :", normdiffvector)
        #print(normdiffvector*shift)
        pos = mm2coords+np.array((shift*normdiffvector))
        #print("pos :", pos)
        #Returning charge with sign based on direction and position
        #Return coords as regular list
        return -q0*direction,list(pos)
    def SetDipoleCharges(self):
        print("Adding extra charges to preserve dipole moment for charge-shifting")
        #Adding 2 dipole pointcharges for each MM2 atom
        self.dipole_charges = []
        self.dipole_coords = []
        #print("self.MMboundarydict : ", self.MMboundarydict)
        for MM1,MMx in self.MMboundarydict.items():
            #print("MM1 :", MM1)
            #print("MMx : ", MMx)
            #Getting original MM1 charge (before set to 0)
            MM1charge = self.charges[MM1]
            #print("MM1atom charge: ", MM1charge)
            MM1charge_fract=MM1charge/len(MMx)
            #print("MM1charge_fract:", MM1charge_fract)
            
            for MM in MMx:
                #print("MM :", MM)
                q_d1, pos_d1 = self.get_dipole_charge(MM1charge_fract,1,MM1,MM)
                #print("q_d1: ", q_d1)
                #print("pos_d1: ", pos_d1)
                q_d2, pos_d2 = self.get_dipole_charge(MM1charge_fract,-1,MM1,MM)
                #print("q_d2: ", q_d2)
                #print("pos_d2: ", pos_d2)
                self.dipole_charges.append(q_d1)
                self.dipole_charges.append(q_d2)
                self.dipole_coords.append(pos_d1)
                self.dipole_coords.append(pos_d2)
    
    def run(self, current_coords=None, elems=None, Grad=False, nprocs=1):
        CheckpointTime = time.time()
        if self.printlevel >= 2:
            print(BC.WARNING, BC.BOLD, "------------RUNNING QM/MM MODULE-------------", BC.END)
            print("QM Module:", self.qm_theory_name)
            print("MM Module:", self.mm_theory_name)

        #If no coords provided to run (from Optimizer or NumFreq or MD) then use coords associated with object.
        #if len(current_coords) != 0:
        if current_coords is not None:
            pass
        else:
            current_coords=self.coords

        if self.embedding=="Elstat":
            PC=True
        else:
            PC=False
        
        #If nprocs was set when calling .run then using, otherwise use self.nprocs
        if nprocs==1:
            nprocs=self.nprocs
        
        if self.printlevel >= 2:
            print("Running QM/MM object with {} cores available".format(nprocs))
        #Updating QM coords and MM coords.
        
        #TODO: Should we use different name for updated QMcoords and MMcoords here??
        self.qmcoords=[current_coords[i] for i in self.qmatoms]
        self.mmcoords=[current_coords[i] for i in self.mmatoms]
        
        self.qmelems=[self.elems[i] for i in self.qmatoms]
        self.mmelems=[self.elems[i] for i in self.mmatoms]
        
        
        
        #LINKATOMS
        #1. Get linkatoms coordinates
        if self.linkatoms==True:
            linkatoms_dict = module_coords.get_linkatom_positions(self.boundaryatoms,self.qmatoms, current_coords, self.elems)
            printdebug("linkatoms_dict:", linkatoms_dict)
            #2. Add linkatom coordinates to qmcoords???
            print("Adding linkatom positions to QM coords")
            

            linkatoms_indices=[]
            
            #Sort by QM atoms:
            printdebug("linkatoms_dict.keys :", linkatoms_dict.keys())
            for pair in sorted(linkatoms_dict.keys()):
                print("Pair :", pair)
                self.qmcoords.append(linkatoms_dict[pair])
                #print("self.qmcoords :", self.qmcoords)
                #print(len(self.qmcoords))
                #exit()
                #Linkatom indices for book-keeping
                linkatoms_indices.append(len(self.qmcoords)-1)
                print("linkatoms_indices: ", linkatoms_indices)
                
            #TODO: Modify qm_elems list. Use self.qmelems or separate qmelems ?
            #TODO: Should we do this at object creation instead?
            current_qmelems=self.qmelems + ['H']*len(linkatoms_dict)
            print("")
            #print("current_qmelems :", current_qmelems)
            
            #Charge-shifting + Dipole thing
            print("Doing charge-shifting...")
            #print("Before: self.pointcharges are: ", self.pointcharges)
            #Do Charge-shifting. MM1 charge distributed to MM2 atoms
            
            self.ShiftMMCharges() # Creates self.pointcharges
            #print("After: self.pointcharges are: ", self.pointcharges)
            print("Num pointcharges for full system: ", len(self.pointcharges))
            
            #TODO: Code alternative to Charge-shifting: L2 scheme which deletes whole charge-group that MM1 belongs to
            
            # Defining pointcharges as only containing MM atoms
            self.pointcharges=[self.pointcharges[i] for i in self.mmatoms]
            #print("After: self.pointcharges are: ", self.pointcharges)
            print("Num pointcharges for MM system: ", len(self.pointcharges))
            #Set 
            self.SetDipoleCharges() #Creates self.dipole_charges and self.dipole_coords

            #Adding dipole charge coords to MM coords (given to QM code) and defining pointchargecoords
            print("Adding {} dipole charges to PC environment".format(len(self.dipole_charges)))
            self.pointchargecoords=self.mmcoords+self.dipole_coords
            
            #Adding dipole charges to MM charges list (given to QM code)
            #TODO: Rename as pcharges list so as not to confuse with what MM code sees??
            self.pointcharges=self.pointcharges+self.dipole_charges
            print("Num pointcharges after dipole addition: ", len(self.pointcharges))
        else:
            #If no linkatoms then use original self.qmelems
            current_qmelems = self.qmelems
            #If no linkatoms then self.pointcharges are just original charges with QM-region zeroed
            #print("self.mmatoms:", self.mmatoms)
            #print("self.charges_qmregionzeroed: ", self.charges_qmregionzeroed)
            self.pointcharges=[self.charges_qmregionzeroed[i] for i in self.mmatoms]
            #If no linkatoms MM coordinates are the same
            self.pointchargecoords=self.mmcoords
       
        #NOTE: Now we have updated MM-coordinates (if doing linkatoms, wtih dipolecharges etc) and updated mm-charges (more, due to dipolecharges if linkatoms)
        # We also have MMcharges that have been set to zero due to QM/mm
        # Choice: should we now delete charges that are zero or not. chemshell does
        #NOTE: do here or have QM-theory do it. probably best to do here (otherwise we have to write multiple QM interface routines)
        

        #Removing zero-valued charges
        #NOTE: Problem, if we remove zero-charges we lose our indexing as the charges removed could be anywhere
        # NOTE: Thus not removing them.
        print("Number of charges :", len(self.pointcharges))
        #print("Removing zero-valued charges")
        #self.pointcharges, self.pointchargecoords = remove_zero_charges(self.pointcharges, self.pointchargecoords)
        print("Number of charge coordinates :", len(self.pointchargecoords))
        print_time_rel(CheckpointTime, modulename='QM/MM run prep')
        
        #If no qmatoms then do MM-only
        if len(self.qmatoms) == 0:
            print("No qmatoms list provided. Setting QMtheory to None")
            self.qm_theory_name="None"
            self.QMenergy=0.0
        
        
        
        if self.qm_theory_name=="ORCATheory":
            #Calling ORCA theory, providing current QM and MM coordinates.
            if Grad==True:
                if PC==True:
                    self.QMenergy, self.QMgradient, self.PCgradient = self.qm_theory.run(current_coords=self.qmcoords,
                                                                                         current_MM_coords=self.pointchargecoords,
                                                                                         MMcharges=self.pointcharges,
                                                                                         qm_elems=current_qmelems,
                                                                                         Grad=True, PC=True, nprocs=nprocs)
                else:
                    self.QMenergy, self.QMgradient = self.qm_theory.run(current_coords=self.qmcoords,
                                                      current_MM_coords=self.pointchargecoords, MMcharges=self.pointcharges,
                                                      qm_elems=current_qmelems, Grad=True, PC=False, nprocs=nprocs)
            else:
                self.QMenergy = self.qm_theory.run(current_coords=self.qmcoords,
                                                      current_MM_coords=self.pointchargecoords, MMcharges=self.pointcharges,
                                                      qm_elems=current_qmelems, Grad=False, PC=PC, nprocs=nprocs)
        elif self.qm_theory_name == "Psi4Theory":
            #Calling Psi4 theory, providing current QM and MM coordinates.
            if Grad==True:
                if PC==True:
                    print(BC.WARNING, "Pointcharge gradient for Psi4 is not implemented.",BC.END)
                    print(BC.WARNING, "Warning: Only calculating QM-region contribution, skipping electrostatic-embedding gradient on pointcharges", BC.END)
                    print(BC.WARNING, "Only makes sense if MM region is frozen! ", BC.END)
                    self.QMenergy, self.QMgradient = self.qm_theory.run(current_coords=self.qmcoords,
                                                                                         current_MM_coords=self.pointchargecoords,
                                                                                         MMcharges=self.pointcharges,
                                                                                         qm_elems=current_qmelems,
                                                                                         Grad=True, PC=True, nprocs=nprocs)
                    #Creating zero-gradient array
                    self.PCgradient = np.zeros((len(self.mmatoms), 3))
                else:
                    print("grad. mech embedding. not ready")
                    exit()
                    self.QMenergy, self.QMgradient = self.qm_theory.run(current_coords=self.qmcoords,
                                                      current_MM_coords=self.pointchargecoords, MMcharges=self.pointcharges,
                                                      qm_elems=current_qmelems, Grad=True, PC=False, nprocs=nprocs)
            else:
                print("grad false.")
                if PC == True:
                    print("PC embed true. not ready")
                    self.QMenergy = self.qm_theory.run(current_coords=self.qmcoords,
                                                      current_MM_coords=self.pointchargecoords, MMcharges=self.pointcharges,
                                                      qm_elems=current_qmelems, Grad=False, PC=PC, nprocs=nprocs)
                else:
                    print("mech true", not ready)
                    exit()


        elif self.qm_theory_name == "xTBTheory":
            #Calling xTB theory, providing current QM and MM coordinates.
            if Grad==True:
                if PC==True:
                    self.QMenergy, self.QMgradient, self.PCgradient = self.qm_theory.run(current_coords=self.qmcoords,
                                                                                         current_MM_coords=self.pointchargecoords,
                                                                                         MMcharges=self.pointcharges,
                                                                                         qm_elems=current_qmelems,
                                                                                         Grad=True, PC=True, nprocs=nprocs)
                else:
                    self.QMenergy, self.QMgradient = self.qm_theory.run(current_coords=self.qmcoords,
                                                      current_MM_coords=self.pointchargecoords, MMcharges=self.pointcharges,
                                                      qm_elems=current_qmelems, Grad=True, PC=False, nprocs=nprocs)
            else:
                self.QMenergy = self.qm_theory.run(current_coords=self.qmcoords,
                                                      current_MM_coords=self.pointchargecoords, MMcharges=self.pointcharges,
                                                      qm_elems=current_qmelems, Grad=False, PC=PC, nprocs=nprocs)


        elif self.qm_theory_name == "DaltonTheory":
            print("not yet implemented")
            exit(1)
        elif self.qm_theory_name == "NWChemtheory":
            print("not yet implemented")
            exit(1)
        elif self.qm_theory_name == "None":
            print("No QMtheory. Skipping QM calc")
            self.QMenergy=0.0;self.linkatoms=False;self.PCgradient=np.array([0.0, 0.0, 0.0])
            self.QMgradient=np.array([0.0, 0.0, 0.0])
        elif self.qm_theory_name == "ZeroTheory":
            self.QMenergy=0.0;self.linkatoms=False;self.PCgradient=np.array([0.0, 0.0, 0.0])
            self.QMgradient=np.array([0.0, 0.0, 0.0])
        else:
            print("invalid QM theory")
            exit(1)
        print_time_rel(CheckpointTime, modulename='QM step')
        CheckpointTime = time.time()



        # MM THEORY
        if self.mm_theory_name == "NonBondedTheory":
            if self.printlevel >= 2:
                print("Running MM theory as part of QM/MM.")
                print("Using MM on full system. Charges for QM region  have to be set to zero ")
                printdebug("Charges for full system is: ", self.charges)
                print("Passing QM atoms to MMtheory run so that QM-QM pairs are skipped in pairlist")
                print("Passing active atoms to MMtheory run so that frozen pairs are skipped in pairlist")
            assert len(current_coords) == len(self.charges_qmregionzeroed)
                
            # NOTE: charges_qmregionzeroed for full system but with QM-charges zeroed (no other modifications)
            #NOTE: Using original system coords here (not with linkatoms, dipole etc.). Also not with deleted zero-charge coordinates. 
            #charges list for full system, can be zeroed but we still want the LJ interaction
                
            self.MMenergy, self.MMgradient= self.mm_theory.run(current_coords=current_coords,
                                                               charges=self.charges_qmregionzeroed, connectivity=self.connectivity,
                                                               qmatoms=self.qmatoms, actatoms=self.actatoms)

        elif self.mm_theory_name == "OpenMMTheory":
            if self.printlevel >= 2:
                print("Running OpenMM theory as part of QM/MM.")
            if self.QMChargesZeroed==True:
                if self.printlevel >= 2:
                    print("Using MM on full system. Charges for QM region {} have been set to zero ".format(self.qmatoms))
            else:
                print("QMCharges have not been zeroed")
                exit(1)
            printdebug("Charges for full system is: ", self.charges)
            #Todo: Need to make sure OpenMM skips QM-QM Lj interaction => Exclude
            #Todo: Need to have OpenMM skip frozen region interaction for speed  => => Exclude
            if Grad==True:
                print("QM/MM Grad is True")
                self.MMenergy, self.MMgradient= self.mm_theory.run(current_coords=current_coords, qmatoms=self.qmatoms, Grad=True)
            else:
                print("QM/MM Grad is false")
                self.MMenergy= self.mm_theory.run(current_coords=current_coords, qmatoms=self.qmatoms)
        else:
            self.MMenergy=0
        print_time_rel(CheckpointTime, modulename='MM step')
        CheckpointTime = time.time()
        #Final QM/MM Energy
        self.QM_MM_energy= self.QMenergy+self.MMenergy
        blankline()
        if self.printlevel >= 2:
            print("{:<20} {:>20.12f}".format("QM energy: ",self.QMenergy))
            print("{:<20} {:>20.12f}".format("MM energy: ", self.MMenergy))
            print("{:<20} {:>20.12f}".format("QM/MM energy: ", self.QM_MM_energy))
        blankline()

        #Final QM/MM gradient. Combine QM gradient, MM gradient and PC-gradient (elstat MM gradient from QM code).
        #First combining QM and PC gradient to one.
        if Grad == True:
            
            #TODO: Deal with linkatom gradient here.
            # Add contribution to QM1 and MM1 contribution???
            
            if self.linkatoms==True:
                #This projects the linkatom force onto the respective QM atom and MM atom
                def linkatom_force_fix(Qcoord, Mcoord, Lcoord, Qgrad,Mgrad,Lgrad):
                    #QM1-L and QM1-MM1 distances
                    QLdistance=module_coords.distance(Qcoord,Lcoord)
                    #print("QLdistance:", QLdistance)
                    MQdistance=module_coords.distance(Mcoord,Qcoord)
                    #print("MQdistance:", MQdistance)
                    #B and C: a 3x3 arrays
                    B=np.zeros([3,3])
                    C=np.zeros([3,3])
                    for i in range(0,2):
                        for j in range(0,2):
                            B[i,j]=-1*QLdistance*(Mcoord[i]-Qcoord[i])*(Mcoord[j]-Qcoord[j]) / (MQdistance*MQdistance*MQdistance)
                    for i in range(0,2):
                        B[i,i] = B[i,i] + QLdistance / MQdistance
                    for i in range(0,2):
                        for j in range(0,2):
                            C[i,j]= -1 * B[i,j]
                    for i in range(0,2):
                        C[i,i] = C[i,i] + 1.0                
                
                    #QM atom gradient
                    #print("Qgrad:", Qgrad)
                    #print("Lgrad:", Lgrad)
                    #print("C: ", C)
                    #print("B:", B)
                    #Multiply grad by C-diagonal
                    Qgrad[0] = Qgrad[0]*C[0][0]
                    Qgrad[1] = Qgrad[1]*C[1][1]
                    Qgrad[2] = Qgrad[2]*C[2][2]
                    
                    #print("Qgrad:", Qgrad)
                    #MM atom gradient
                    #print("Mgrad:", Mgrad)
                    Mgrad[0] = Mgrad[0]*B[0][0]
                    Mgrad[1] = Mgrad[1]*B[1][1]
                    Mgrad[2] = Mgrad[2]*B[2][2]                    
                    #print("Mgrad:", Mgrad)
                    
                    return Qgrad,Mgrad
                
                def fullindex_to_qmindex(fullindex,qmatoms):
                    qmindex=qmatoms.index(fullindex)
                    return qmindex
                
                #print("here")
                #print("linkatoms_dict: ", linkatoms_dict)
                #print("linkatoms_indices: ", linkatoms_indices)
                num_linkatoms=len(linkatoms_indices)
                for pair in sorted(linkatoms_dict.keys()):
                    #print("pair: ", pair)
                    linkatomindex=linkatoms_indices.pop(0)
                    #print("linkatomindex:", linkatomindex)
                    Lgrad=self.QMgradient[linkatomindex]
                    #print("Lgrad:",Lgrad)
                    Lcoord=linkatoms_dict[pair]
                    #print("Lcoord:", Lcoord)
                    fullatomindex_qm=pair[0]
                    #print("fullatomindex_qm:", fullatomindex_qm)
                    #print("self.qmatoms:", self.qmatoms)
                    qmatomindex=fullindex_to_qmindex(fullatomindex_qm,self.qmatoms)
                    #print("qmatomindex:", qmatomindex)
                    fullatomindex_mm=pair[1]
                    #print("fullatomindex_mm:", fullatomindex_mm)
                    Qcoord=self.qmcoords[qmatomindex]
                    #print("Qcoords: ", Qcoord)
                    #print("type self.QMGradient", type(self.QMgradient))
                    Qgrad=self.QMgradient[qmatomindex]
                    #print("Qgrad:", Qgrad)
                    
                    #print("length of self.MMgradient:", len(self.MMgradient))
                    Mcoord=current_coords[fullatomindex_mm]
                    #print("Mcoord:", Mcoord)
                    #print("type self.MMgradient", type(self.MMgradient))
                    #print("fullatomindex_mm:", fullatomindex_mm)
                    Mgrad=self.MMgradient[fullatomindex_mm]
                    #print("Mgrad: ", Mgrad)
                    Qgrad,Mgrad= linkatom_force_fix(Qcoord, Mcoord, Lcoord, Qgrad,Mgrad,Lgrad)
                    #print("Qgrad: ", Qgrad)
                    #print("Mgrad: ", Mgrad)
                    self.QMgradient[qmatomindex]=Qgrad
                    self.MMgradient[fullatomindex_mm]=Mgrad
                #Fix QMgradient by removing linkatom contributions (bottom)
                #Redundant?
                #print("self.QMgradient:", self.QMgradient)
                self.QMgradient=self.QMgradient[0:-num_linkatoms] #remove linkatoms
                #print("self.QMgradient:", self.QMgradient)
            
                # QM_PC_gradient is system size. Combining QM part (after linkatom-contribution removed) and PC part into 
                #print("self.allatoms:", len(self.allatoms))
                #print("len(self.QMgradient) :", len(self.QMgradient))
                #print("len(self.MMgradient) :", len(self.MMgradient))
                #print("length self.PCgradient ", len(self.PCgradient))
            
                assert len(self.allatoms) == len(self.MMgradient)
                assert len(self.QMgradient) + len(self.PCgradient) - len(self.dipole_charges)  == len(self.MMgradient)
            
            self.QM_PC_gradient = np.zeros((len(self.MMgradient), 3))
            qmcount=0;pccount=0
            for i in self.allatoms:
                if i in self.qmatoms:
                    #QM-gradient. Linkatom gradients are skipped
                    self.QM_PC_gradient[i]=self.QMgradient[qmcount]
                    qmcount+=1
                else:
                    #Pointcharge-gradient. Dipole-charge gradients are skipped (never reached)
                    self.QM_PC_gradient[i] = self.PCgradient[pccount]
                    pccount += 1
            
            #print("qmcount:", qmcount)
            #print("pccount:", pccount)
            #print("self.QM_PC_gradient len ", len(self.QM_PC_gradient))
            assert qmcount == len(self.qmatoms)
            assert pccount == len(self.mmatoms)
            
            #Now assemble final QM/MM gradient
            assert len(self.QM_PC_gradient) == len(self.MMgradient)
            self.QM_MM_gradient=self.QM_PC_gradient+self.MMgradient
            #print_time_rel(CheckpointTime, modulename='QM/MM gradient combine')
            if self.printlevel >=3:
                print("Printlevel >=3: Printing all gradients to disk")
                #print("QM gradient (au/Bohr):")
                #module_coords.print_coords_all(self.QMgradient, self.qmelems, self.qmatoms)
                module_coords.write_coords_all(self.QMgradient, self.qmelems, indices=self.qmatoms, file="QMgradient", description="QM gradient (au/Bohr):")
                #blankline()
                #print("PC gradient (au/Bohr):")
                #module_coords.print_coords_all(self.PCgradient, self.mmelems, self.mmatoms)
                module_coords.write_coords_all(self.PCgradient, self.mmelems, indices=self.mmatoms, file="PCgradient", description="PC gradient (au/Bohr):")
                #blankline()
                #print("QM+PC gradient (au/Bohr):")
                #module_coords.print_coords_all(self.QM_PC_gradient, self.elems, self.allatoms)
                module_coords.write_coords_all(self.QM_PC_gradient, self.elems, indices=self.allatoms, file="QM+PCgradient", description="QM+PC gradient (au/Bohr):")
                #blankline()
                #print("MM gradient (au/Bohr):")
                #module_coords.print_coords_all(self.MMgradient, self.elems, self.allatoms)
                module_coords.write_coords_all(self.MMgradient, self.elems, indices=self.allatoms, file="MMgradient", description="MM gradient (au/Bohr):")
                #blankline()
                #print("Total QM/MM gradient (au/Bohr):")
                #print("")
                #module_coords.print_coords_all(self.QM_MM_gradient, self.elems,self.allatoms)
                module_coords.write_coords_all(self.QM_MM_gradient, self.elems, indices=self.allatoms, file="QM_MMgradient", description="QM/MM gradient (au/Bohr):")
            if self.printlevel >= 2:
                print(BC.WARNING,BC.BOLD,"------------ENDING QM/MM MODULE-------------",BC.END)
            return self.QM_MM_energy, self.QM_MM_gradient
        else:
            return self.QM_MM_energy











#Micro-iterative QM/MM Optimization
# NOTE: Not ready
#Wrapper around QM/MM run and geometric optimizer for performing microiterative QM/MM opt
# I think this is easiest
# Thiel: https://pubs.acs.org/doi/10.1021/ct600346p
#Look into new: https://pubs.acs.org/doi/pdf/10.1021/acs.jctc.6b00547

def microiter_QM_MM_OPT_v1(theory=None, fragment=None, chargemodel=None, qmregion=None, activeregion=None, bufferregion=None):
    
    exit()
    #1. Calculate single-point QM/MM job and get charges. Maybe get gradient to judge convergence ?
    energy=Singlepoint(theory=theory,fragment=fragment)
    #grab charges
    #update charges
    #2. Change active region so that only MM atoms are in active region
    conv_criteria="something"
    sdf=geomeTRICOptimizer(theory=theory,fragment=fragment, coordsystem='hdlc', maxiter=50, ActiveRegion=False, actatoms=[], 
                           convergence_setting=None, conv_criteria=conv_criteria)
    #3. QM/MM single-point with new charges?
    #3b. Or do geometric job until a certain threshold and then do MM again??


#frozen-density micro-iterative QM/MM
def microiter_QM_MM_OPT_v2(theory=None, fragment=None, maxiter=500, qmregion=None, activeregion=None, bufferregion=None,xtbdir=None,xtbmethod='GFN2-xTB'):
    sdf="dsds"
    exit()
#xtb instead of charges
def microiter_QM_MM_OPT_v3(theory=None, fragment=None, maxiter=500, qmregion=None, activeregion=None, bufferregion=None,xtbdir=None,xtbmethod='GFN2-xTB'):
    exit()
    #Make copy of orig theory
    orig_theory=copy.deepcopy(theory)
    # TODO: If BS-spinflipping, use Hsmult instead of regular mul6
    xtbtheory=xTBTheory(xtbdir=None, charge=theory.qm_theory.charge, mult=theory.qm_theory.mult, xtbmethod=xtbmethod, 
                        runmode='inputfile', nprocs=1, printlevel=2)
    ll_theory=copy.deepcopy(theory)
    ll_theory.qm_theory=xtbtheory
    #Convergence criteria
    loose_conv_criteria = { 'convergence_energy' : 1e-1, 'convergence_grms' : 1e-1, 'convergence_gmax' : 1e-1, 'convergence_drms' : 1e-1, 
                     'convergence_dmax' : 1e-1 }
    final_conv_criteria = {'convergence_energy' : 1e-6, 'convergence_grms' : 3e-4, 'convergence_gmax' : 4.5e-4, 'convergence_drms' : 1.2e-3, 
                        'convergence_dmax' : 1.8e-3 }

    
    #Remove QM-region from actregion, optimize everything else.
    act_original=copy.deepcopy(act)
    for i in qmatoms:
        activeregion.remove(i)
        
        
    for macroiteration in range(0,maxiter):
        oldHLenergy=Hlenergy
        print("oldHLenergy:", oldHLenergy)
        #New Macro-iteration step
        HLenergy,HLgrad=Singlepoint(theory=orig_theory,fragment=fragment,Grad=True)
        print("HLenergy:", HLenergy)
        #Check if HLgrad matches convergence critera for gradient?
        if macroiteration > 0:
            #Test step acceptance
            if HLenergy > oldHLenergy:
                #Reject step. Reduce step size, use old geo, not sure how
                pass
            if RMS_Hlgrad < final_conv_criteria['convergence_grms'] and MaxHLgrad < final_conv_criteria['convergence_gmax']:
                print("Converged.")
                return
            #Make step using Hlgrad
            
        LLenergy,LLgrad=Singlepoint(theory=ll_theory,fragment=fragment,Grad=True)
        #Compare gradient, calculate G0 correction

        print("Now starting low-level theory QM/MM microtierative optimization")
        print("activeregion:", activeregion)
        print("ll_theory qm theory:", ll_theory.qm_theory)
        bla=geomeTRICOptimizer(theory=ll_theory,fragment=fragment, coordsystem='hdlc', maxiter=200, ActiveRegion=True, actatoms=activeregion, 
                            conv_criteria=loose_conv_criteria)
        print("Now starting finallevel theory QM/MM microtierative optimization")
        print("act_original:", act_original)
        print("orig_theory qm theory:", orig_theory.qm_theory)
        final=geomeTRICOptimizer(theory=orig_theory,fragment=fragment, coordsystem='hdlc', maxiter=200, ActiveRegion=True, actatoms=act_original, 
                            conv_criteria=final_conv_criteria)
        print("Micro-iterative QM/MM opt complete !")
    return final
    