import copy
import time
import numpy as np
import math

#functions related to QM/MM
import modules.module_coords
from functions.functions_general import ashexit, BC,blankline,listdiff,print_time_rel,printdebug,print_line_with_mainheader,writelisttofile
import settings_ash

#QM/MM theory object.
#Required at init: qm_theory and qmatoms. Fragment not. Can come later
#TODO NOTE: If we add init arguments, remember to update Numfreq QMMM option as it depends on the keywords
class QMMMTheory:
    def __init__(self, qm_theory=None, qmatoms=None, fragment=None, mm_theory=None, charges=None,
                 embedding="Elstat", printlevel=2, numcores=1, actatoms=None, frozenatoms=None, excludeboundaryatomlist=None,
                 unusualboundary=False, openmm_externalforce=False, TruncatedPC=False, TruncPCRadius=55, TruncatedPC_recalc_iter=50,
                qm_charge=None, qm_mult=None):
        module_init_time=time.time()
        timeA=time.time()
        print_line_with_mainheader("QM/MM Theory")
        #print(BC.WARNING,BC.BOLD,"------------Defining QM/MM object-------------", BC.END)

        #Defining charge/mult of QM-region
        self.qm_charge=qm_charge
        self.qm_mult=qm_mult

        #Indicate that this is a hybrid QM/MM type theory
        self.theorytype="QM/MM"

        #External force energy. ALways zero except when using openmm_externalforce
        self.extforce_energy=0.0


        #Linkatoms False by default. Later checked.
        self.linkatoms=False

        #Whether we are using OpenMM custom external forces or not
        #NOTE: affects runmode
        self.openmm_externalforce=openmm_externalforce

        #Theory level definitions
        self.printlevel=printlevel
        print("self.printlevel: ", self.printlevel)
        self.qm_theory=qm_theory
        self.qm_theory_name = self.qm_theory.__class__.__name__
        self.mm_theory=mm_theory
        self.mm_theory_name = self.mm_theory.__class__.__name__
        if self.mm_theory_name == "str":
            self.mm_theory_name="None"

        print("QM-theory:", self.qm_theory_name)
        print("MM-theory:", self.mm_theory_name)

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

            # FROZEN AND ACTIVE ATOM REGIONS for NonbondedTheory
            if self.mm_theory_name == "NonBondedTheory":
                #NOTE: To be looked at. actatoms and frozenatoms have no meaning in OpenMMTHeory. NonbondedTheory, however.
                if actatoms is None and frozenatoms is None:
                    #print("Actatoms/frozenatoms list not passed to QM/MM object. Will do all frozen interactions in MM (expensive).")
                    #print("All {} atoms active, no atoms frozen in QM/MM definition (may not be frozen in optimizer)".format(len(self.allatoms)))
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
                    ashexit()
            
            #print("List of all atoms:", self.allatoms)
            print("QM region ({} atoms): {}".format(len(self.qmatoms),self.qmatoms))
            print("MM region ({} atoms)".format(len(self.mmatoms)))
            print_time_rel(timeA, modulename="Region setup")
            timeA=time.time()
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
            ashexit()

        #Setting QM/MM qmatoms in QMtheory also (used for Spin-flipping currently)
        self.qm_theory.qmatoms=self.qmatoms

        
        #Setting numcores of object.
        #This will be when calling QMtheory and probably MMtheory
        
        #numcores-setting in QMMMTheory takes precedent
        if numcores != 1:
            self.numcores=numcores
        #If QMtheory numcores was set (and QMMMTHeory not)
        elif self.qm_theory.numcores != 1:
            self.numcores=self.qm_theory.numcores
        #Default 1 proc
        else:
            self.numcores=1
        print("QM/MM object selected to use {} cores".format(self.numcores))

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
                ashexit()
        else:
            print("Reading in charges")
            if len(charges) != len(fragment.atomlist):
                print(BC.FAIL,"Number of charges not matching number of fragment atoms. Exiting.",BC.END)
                ashexit()
            self.charges=charges
        
        if len(self.charges) == 0:
            print("No charges present in QM/MM object. Exiting...")
            ashexit()
        

        #Flag to check whether QMCharges have been zeroed in self.charges_qmregionzeroed list
        self.QMChargesZeroed=False

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

        #Truncated PC-region option 
        self.TruncatedPC=TruncatedPC
        self.TruncPCRadius=TruncPCRadius
        self.TruncatedPCcalls=0
        self.TruncatedPCflag=False
        self.TruncatedPC_recalc_iter=TruncatedPC_recalc_iter

        if self.TruncatedPC is True:
            print("Truncated PC approximation in QM/MM is active.")
            print("TruncPCRadius:", self.TruncPCRadius)
            print("TruncPC Recalculation iteration:", self.TruncatedPC_recalc_iter)

        #If MM THEORY (not just pointcharges)
        if mm_theory is not None:

            #Sanity check. Same number of atoms in fragment and MM object ?
            if fragment.numatoms != mm_theory.numatoms:
                print("")
                print(BC.FAIL,"Number of atoms in fragment ({}) and MMtheory object differ ({})".format(fragment.numatoms,mm_theory.numatoms),BC.END)
                print(BC.FAIL,"This does not make sense. Check coordinates and forcefield files. Exiting...", BC.END)
                ashexit()

            #Add possible exception for QM-QM atoms here.
            #Maybe easier to just just set charges to 0. LJ for QM-QM still needs to be done by MM code
            #if self.mm_theory_name == "OpenMMTheory":
            #           
                #print("Now adding exceptions for frozen atoms")
                #if len(self.frozenatoms) > 0:
                #    print("Here adding exceptions for OpenMM")
                #    print("Frozen-atom exceptions currently inactive...")
                    #print("Num frozen atoms: ", len(self.frozenatoms))
                    #Disabling for now, since so bloody slow. Need to speed up
                    #mm_theory.addexceptions(self.frozenatoms)


            #Check if we need linkatoms by getting boundary atoms dict:
            blankline()

            #Update: Tolerance modification to make sure we definitely catch connected atoms and get QM-MM boundary right.
            #Scale=1.0 and tol=0.1 fails for S-C bond in rubredoxin from a classical MD run
            #Bumping up a bit here
            conn_scale=settings_ash.settings_dict["scale"]
            conn_tolerance=settings_ash.settings_dict["tol"]+0.1
            self.boundaryatoms = modules.module_coords.get_boundary_atoms(self.qmatoms, self.coords, self.elems, conn_scale, 
                conn_tolerance, excludeboundaryatomlist=excludeboundaryatomlist, unusualboundary=unusualboundary)
            if len(self.boundaryatoms) >0:
                print("Found covalent QM-MM boundary. Linkatoms option set to True")
                print("Boundaryatoms (QM:MM pairs):", self.boundaryatoms)
                print("Note: used connectivity settings, scale={} and tol={} to determine boundary.".format(conn_scale,conn_tolerance))
                self.linkatoms=True
                #Get MM boundary information. Stored as self.MMboundarydict
                self.get_MMboundary(conn_scale,conn_tolerance)
            else:
                print("No covalent QM-MM boundary. Linkatoms option set to False")
                self.linkatoms=False
            
            #Removing possible QM atom constraints in OpenMMTheory
            #Will only apply when running OpenMM_Opt or OpenMM_MD
            if self.mm_theory_name == "OpenMMTheory":
                self.mm_theory.remove_constraints_for_atoms(self.qmatoms)

            #Remove bonded interactions in MM part. Only in OpenMM. Assuming they were never defined in NonbondedTHeory
                print("Removing bonded terms for QM-region in MMtheory")
                self.mm_theory.modify_bonded_forces(self.qmatoms)

                #NOTE: Temporary. Adding exceptions for nonbonded QM atoms. Will ignore QM-QM Coulomb and LJ interactions. 
                #NOTE: For QM-MM interactions Coulomb charges are zeroed below (update_charges and delete_exceptions)
                print("Removing nonbonded terms for QM-region in MMtheory (QM-QM interactions)")
                self.mm_theory.addexceptions(self.qmatoms)
                
            #Change charges
            # Keeping self.charges as originally defined.
            #Setting QM charges to 0 since electrostatic embedding
            #and Charge-shift QM-MM boundary
                
            #Zero QM charges
            #TODO: DO here or inside run instead?? Needed for MM code.
            self.ZeroQMCharges() #Modifies self.charges_qmregionzeroed
            #print("length of self.charges_qmregionzeroed :", len(self.charges_qmregionzeroed))
                
            #TODO: make sure this works for OpenMM and for NonBondedTheory
            # Updating charges in MM object. 
            self.mm_theory.update_charges(self.qmatoms,[0.0 for i in self.qmatoms])

            if self.mm_theory_name == "OpenMMTheory":
                #Deleting Coulomb exception interactions involving QM and MM atoms
                self.mm_theory.delete_exceptions(self.qmatoms)
                #Option to create OpenMM externalforce that handles full system
                if openmm_externalforce == True:
                    print("openmm_externalforce is True")
                    print("Creating new OpenMM custom external force")
                    self.openmm_externalforceobject = self.mm_theory.add_custom_external_force()

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
        print_time_rel(module_init_time, modulename='QM/MM object creation', moduleindex=2)
    #From QM1:MM1 boundary dict, get MM1:MMx boundary dict (atoms connected to MM1)
    def get_MMboundary(self,scale,tol):
        timeA=time.time()
        # if boundarydict is not empty we need to zero MM1 charge and distribute charge from MM1 atom to MM2,MM3,MM4
        #Creating dictionary for each MM1 atom and its connected atoms: MM2-4
        self.MMboundarydict={}
        for (QM1atom,MM1atom) in self.boundaryatoms.items():
            connatoms = modules.module_coords.get_connected_atoms(self.coords, self.elems, scale,tol, MM1atom)
            #Deleting QM-atom from connatoms list
            connatoms.remove(QM1atom)
            self.MMboundarydict[MM1atom] = connatoms
        print("")
        print("MM boundary (MM1:MMx pairs):", self.MMboundarydict)
        print_time_rel(timeA, modulename="get_MMboundary")
    # Set QMcharges to Zero and shift charges at boundary
    #TODO: Add both L2 scheme (delete whole charge-group of M1) and charge-shifting scheme (shift charges to Mx atoms and add dipoles for each Mx atom)
    
    def ZeroQMCharges(self):
        timeA=time.time()
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
        print_time_rel(timeA, modulename="ZeroQMCharges")
    def ShiftMMCharges(self):
        timeA=time.time()
        print("Shifting MM charges at QM-MM boundary.")
        #print("len self.charges_qmregionzeroed: ", len(self.charges_qmregionzeroed))
        #print("len self.charges: ", len(self.charges))
        
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
        print_time_rel(timeA, modulename="ShiftMMCharges")
    #Create dipole charge (twice) for each MM2 atom that gets fraction of MM1 charge
    def get_dipole_charge(self,delq,direction,mm1index,mm2index):
        #timeA=time.time()
        #Distance between MM1 and MM2
        MM_distance = modules.module_coords.distance_between_atoms(fragment=self.fragment, atom1=mm1index, atom2=mm2index)
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
        #print_time_rel(timeA, modulename="get_dipole_charge")
        return -q0*direction,list(pos)
    def SetDipoleCharges(self):
        timeA=time.time()
        print("Adding extra charges to preserve dipole moment for charge-shifting")
        #Adding 2 dipole pointcharges for each MM2 atom
        self.dipole_charges = []
        self.dipole_coords = []
        for MM1,MMx in self.MMboundarydict.items():
            #Getting original MM1 charge (before set to 0)
            MM1charge = self.charges[MM1]
            MM1charge_fract=MM1charge/len(MMx)
            
            for MM in MMx:
                q_d1, pos_d1 = self.get_dipole_charge(MM1charge_fract,1,MM1,MM)
                q_d2, pos_d2 = self.get_dipole_charge(MM1charge_fract,-1,MM1,MM)
                self.dipole_charges.append(q_d1)
                self.dipole_charges.append(q_d2)
                self.dipole_coords.append(pos_d1)
                self.dipole_coords.append(pos_d2)
        print_time_rel(timeA, modulename="SetDipoleCharges")

    #TruncatedPCfunction control flow for pointcharge field passed to QM program
    def TruncatedPCfunction(self):
        self.TruncatedPCcalls+=1
        print("Activating TruncatedPC approximation!")
        if self.TruncatedPCcalls == 1:
            self.TruncatedPCflag=False
            print("This is first QM/MM run. Will use full PC field in this iteration")
            #Origin coords point is center of QM-region
            origincoords=modules.module_coords.get_centroid(self.qmcoords)
            #Determine the indices associated with the truncated PC field once
            self.determine_truncatedPC_indices(origincoords)
            print("Truncated PC-region size: {} charges".format(len(self.truncated_PC_region_indices)))
        elif self.TruncatedPCcalls % self.TruncatedPC_recalc_iter == 0:
            self.TruncatedPCflag=False
            print("This is QM/MM run no. {}. Will use full PC field in this iteration.".format(self.TruncatedPCcalls))
        else:
            self.TruncatedPCflag=True
            print("This is QM/MM run no. {}. Using approximate truncated PC field: {} charges".format(self.TruncatedPCcalls,len(self.truncated_PC_region_indices)))
            self.pointcharges=[self.pointcharges[i] for i in self.truncated_PC_region_indices]
            self.pointchargecoords=np.take(self.pointchargecoords, self.truncated_PC_region_indices, axis=0)

    #Determine truncated PC field indices based on initial coordinates
    #Coordinates and charges for each Opt cycle defined later.
    def determine_truncatedPC_indices(self,origincoords):
        region_indices=[]
        for index,allc in enumerate(self.pointchargecoords):
            dist=modules.module_coords.distance(origincoords,allc)
            if dist < self.TruncPCRadius:
                region_indices.append(index)
        #Only unique and sorting:
        self.truncated_PC_region_indices = np.unique(region_indices).tolist()

    #This update the calculated truncated PC gradient to be full-system gradient
    #by combining with the original 1st step gradient
    def TruncatedPCgradientupdate(self):
        self.newfullPCgradient=copy.copy(self.full_PCgradient)
        print("self.newfullPCgradient len:", len(self.newfullPCgradient))
        for count,trunc_index in enumerate(self.truncated_PC_region_indices):
            self.newfullPCgradient[trunc_index]=self.PCgradient[count]
        self.PCgradient=self.newfullPCgradient


    def run(self, current_coords=None, elems=None, Grad=False, numcores=1, exit_after_customexternalforce_update=False, label=None, charge=None, mult=None):
        module_init_time=time.time()
        CheckpointTime = time.time()
        if self.printlevel >= 2:
            print(BC.WARNING, BC.BOLD, "------------RUNNING QM/MM MODULE-------------", BC.END)
            print("QM Module:", self.qm_theory_name)
            print("MM Module:", self.mm_theory_name)

        #OPTION: QM-region charge/mult from QMMMTheory definition
        #PRIORITY ??
        if self.qm_charge != None:
            print("Charge provided from QMMMTheory object: ", self.qm_charge)
            charge=self.qm_charge
        if self.qm_mult != None:
            print("Mult provided from QMMMTheory object: ", self.qm_mult)
            mult=self.qm_mult

        #Checking if charge and mult has been provided
        if charge == None or mult == None:
            print(BC.FAIL, "Error. charge and mult has not been defined for QMMMTheory.run method", BC.END)
            ashexit()
        print("QM-region charge: {} mult:{}".format(charge,mult))


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
        
        #If numcores was set when calling .run then using, otherwise use self.numcores
        if numcores==1:
            numcores=self.numcores
        
        if self.printlevel >= 2:
            print("Running QM/MM object with {} cores available".format(numcores))
        #Updating QM coords and MM coords.
        
        #TODO: Should we use different name for updated QMcoords and MMcoords here??
        #self.qmcoords=[current_coords[i] for i in self.qmatoms]
        #self.mmcoords=[current_coords[i] for i in self.mmatoms]
        self.qmcoords=np.take(current_coords,self.qmatoms,axis=0)
        self.mmcoords=np.take(current_coords,self.mmatoms,axis=0)

        self.qmelems=[self.elems[i] for i in self.qmatoms]
        self.mmelems=[self.elems[i] for i in self.mmatoms]
        
        
        
        #LINKATOMS
        #1. Get linkatoms coordinates
        if self.linkatoms==True:
            linkatoms_dict = modules.module_coords.get_linkatom_positions(self.boundaryatoms,self.qmatoms, current_coords, self.elems)
            printdebug("linkatoms_dict:", linkatoms_dict)
            #2. Add linkatom coordinates to qmcoords???
            print("Adding linkatom positions to QM coords")
            linkatoms_indices=[]
            
            #Sort by QM atoms:
            printdebug("linkatoms_dict.keys :", linkatoms_dict.keys())
            for pair in sorted(linkatoms_dict.keys()):
                printdebug("Pair :", pair)
                #self.qmcoords.append(linkatoms_dict[pair])
                self.qmcoords = np.append(self.qmcoords,np.array([linkatoms_dict[pair]]), axis=0)
                #print("self.qmcoords :", self.qmcoords)
                #print(len(self.qmcoords))
                #ashexit()
                #Linkatom indices for book-keeping
                linkatoms_indices.append(len(self.qmcoords)-1)
                printdebug("linkatoms_indices: ", linkatoms_indices)
            
            num_linkatoms=len(linkatoms_indices)
            
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
            print("Number of pointcharges for full system: ", len(self.pointcharges))

            #TODO: Code alternative to Charge-shifting: L2 scheme which deletes whole charge-group that MM1 belongs to
            
            # Defining pointcharges as only containing MM atoms
            print("Number of MM atoms:", len(self.mmatoms))
            self.pointcharges=[self.pointcharges[i] for i in self.mmatoms]
            #print("After: self.pointcharges are: ", self.pointcharges)
            print("Number of pointcharges for MM system: ", len(self.pointcharges))
            #Set 
            self.SetDipoleCharges() #Creates self.dipole_charges and self.dipole_coords

            #Adding dipole charge coords to MM coords (given to QM code) and defining pointchargecoords
            print("Adding {} dipole charges to PC environment".format(len(self.dipole_charges)))
            #self.pointchargecoords=self.mmcoords+self.dipole_coords
            self.pointchargecoords=np.append(self.mmcoords,np.array(self.dipole_coords), axis=0)
            #Adding dipole charges to MM charges list (given to QM code)
            #TODO: Rename as pcharges list so as not to confuse with what MM code sees??
            self.pointcharges=self.pointcharges+self.dipole_charges
            print("Number of pointcharges after dipole addition: ", len(self.pointcharges))
        else:
            num_linkatoms=0
            #If no linkatoms then use original self.qmelems
            current_qmelems = self.qmelems
            #If no linkatoms then self.pointcharges are just original charges with QM-region zeroed
            self.pointcharges=[self.charges_qmregionzeroed[i] for i in self.mmatoms]
            #If no linkatoms MM coordinates are the same
            self.pointchargecoords=self.mmcoords
       
        #NOTE: Now we have updated MM-coordinates (if doing linkatoms, wtih dipolecharges etc) and updated mm-charges (more, due to dipolecharges if linkatoms)
        # We also have MMcharges that have been set to zero due to QM/mm
        #We do not delete charges but set to zero

        print("Number of charges:", len(self.pointcharges))
        print("Number of charge coordinates:", len(self.pointchargecoords))

        #TRUNCATED PC Option: Speeding up QM/MM jobs of large systems by passing only a truncated PC field to the QM-code most of the time
        # Speeds up QM-pointcharge gradient that otherwise dominates
        if self.TruncatedPC is True:
            self.TruncatedPCfunction()
            #Modifies self.pointcharges and self.pointchargecoords
            print("Number of charges after truncation :", len(self.pointcharges))
            print("Number of charge coordinates after truncation :", len(self.pointchargecoords))
        
        
        #If no qmatoms then do MM-only
        if len(self.qmatoms) == 0:
            print("No qmatoms list provided. Setting QMtheory to None")
            self.qm_theory_name="None"
            self.QMenergy=0.0
        
        print_time_rel(CheckpointTime, modulename='QM/MM run prep', moduleindex=2)

        if self.qm_theory_name=="ORCATheory":
            #Calling ORCA theory, providing current QM and MM coordinates.
            if Grad==True:
                if PC==True:
                    self.QMenergy, self.QMgradient, self.PCgradient = self.qm_theory.run(current_coords=self.qmcoords,
                                                                                         current_MM_coords=self.pointchargecoords,
                                                                                         MMcharges=self.pointcharges,
                                                                                         qm_elems=current_qmelems, charge=charge, mult=mult,
                                                                                         Grad=True, PC=True, numcores=numcores)
                else:
                    self.QMenergy, self.QMgradient = self.qm_theory.run(current_coords=self.qmcoords,
                                                      current_MM_coords=self.pointchargecoords, MMcharges=self.pointcharges,
                                                      qm_elems=current_qmelems, Grad=True, PC=False, numcores=numcores, charge=charge, mult=mult)
            else:
                self.QMenergy = self.qm_theory.run(current_coords=self.qmcoords,
                                                      current_MM_coords=self.pointchargecoords, MMcharges=self.pointcharges,
                                                      qm_elems=current_qmelems, Grad=False, PC=PC, numcores=numcores, charge=charge, mult=mult)
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
                                                                                         qm_elems=current_qmelems, charge=charge, mult=mult,
                                                                                         Grad=True, PC=True, numcores=numcores)
                    #Creating zero-gradient array
                    self.PCgradient = np.zeros((len(self.mmatoms), 3))
                else:
                    print("grad. mech embedding. not ready")
                    ashexit()
                    self.QMenergy, self.QMgradient = self.qm_theory.run(current_coords=self.qmcoords,
                                                      current_MM_coords=self.pointchargecoords, MMcharges=self.pointcharges, charge=charge, mult=mult,
                                                      qm_elems=current_qmelems, Grad=True, PC=False, numcores=numcores)
            else:
                print("grad false.")
                if PC == True:
                    print("PC embed true. not ready")
                    self.QMenergy = self.qm_theory.run(current_coords=self.qmcoords,
                                                      current_MM_coords=self.pointchargecoords, MMcharges=self.pointcharges, charge=charge, mult=mult,
                                                      qm_elems=current_qmelems, Grad=False, PC=PC, numcores=numcores)
                else:
                    print("mech true", not ready)
                    ashexit()


        elif self.qm_theory_name == "xTBTheory":
            #Calling xTB theory, providing current QM and MM coordinates.
            if Grad==True:
                if PC==True:
                    self.QMenergy, self.QMgradient, self.PCgradient = self.qm_theory.run(current_coords=self.qmcoords,
                                                                                         current_MM_coords=self.pointchargecoords,
                                                                                         MMcharges=self.pointcharges,
                                                                                         qm_elems=current_qmelems, charge=charge, mult=mult,
                                                                                         Grad=True, PC=True, numcores=numcores)
                else:
                    self.QMenergy, self.QMgradient = self.qm_theory.run(current_coords=self.qmcoords,
                                                      current_MM_coords=self.pointchargecoords, MMcharges=self.pointcharges, charge=charge, mult=mult,
                                                      qm_elems=current_qmelems, Grad=True, PC=False, numcores=numcores)
            else:
                self.QMenergy = self.qm_theory.run(current_coords=self.qmcoords,
                                                      current_MM_coords=self.pointchargecoords, MMcharges=self.pointcharges, charge=charge, mult=mult,
                                                      qm_elems=current_qmelems, Grad=False, PC=PC, numcores=numcores)


        elif self.qm_theory_name == "DaltonTheory":
            print("not yet implemented")
            ashexit()
        elif self.qm_theory_name == "NWChemtheory":
            print("not yet implemented")
            ashexit()
        elif self.qm_theory_name == "None":
            print("No QMtheory. Skipping QM calc")
            self.QMenergy=0.0;self.linkatoms=False;self.PCgradient=np.array([0.0, 0.0, 0.0])
            self.QMgradient=np.array([0.0, 0.0, 0.0])
        elif self.qm_theory_name == "ZeroTheory":
            self.QMenergy=0.0;self.linkatoms=False;self.PCgradient=np.array([0.0, 0.0, 0.0])
            self.QMgradient=np.array([0.0, 0.0, 0.0])
        else:
            print("invalid QM theory")
            ashexit()
        print_time_rel(CheckpointTime, modulename='QM step', moduleindex=2)
        CheckpointTime = time.time()

        #Final QM/MM gradient. Combine QM gradient, MM gradient, PC-gradient (elstat MM gradient from QM code).
        # Do linkatom force projections in the end
        #UPDATE: Do MM step in the end now so that we have options for OpenMM extern force
        if Grad == True:
            #TRUNCATED PC Option:
            #Taking calculated truncated PC gradient (self.PCgradient) and combining with original-calculated (e.g. first Opt-step) full PC gradient 
            if self.TruncatedPC is True:
                #If Truncated PC was used in this iteration
                if self.TruncatedPCflag is True:
                    CheckpointTime = time.time()
                    self.TruncatedPCgradientupdate()
                    print_time_rel(CheckpointTime, modulename='trunc pcgrad update', moduleindex=3)
                else:
                    #Full PC gradient was used in this iteration. Storing full PC gradient.
                    self.full_PCgradient=copy.copy(self.PCgradient)

            #assert len(self.allatoms) == len(self.MMgradient)
            
            #Defining QMgradient without linkatoms if present
            if self.linkatoms==True:
                self.QMgradient_wo_linkatoms=self.QMgradient[0:-num_linkatoms] #remove linkatoms
                #Sanity check
                assert len(self.QMgradient_wo_linkatoms) + len(self.PCgradient) - len(self.dipole_charges)  == len(self.allatoms)
            else:
                self.QMgradient_wo_linkatoms=self.QMgradient

            #if self.printlevel >= 2:
            #    modules.module_coords.write_coords_all(self.QMgradient_wo_linkatoms, self.qmelems, indices=self.allatoms, file="QMgradient_wo_linkatoms", description="QM+ gradient withoutlinkatoms (au/Bohr):")


            #Initialize QM_PC gradient (has full system size) and fill up
            #TODO: This can be made more efficient
            self.QM_PC_gradient = np.zeros((len(self.allatoms), 3))
            qmcount=0;pccount=0
            for i in self.allatoms:
                if i in self.qmatoms:
                    #QM-gradient. Linkatom gradients are skipped
                    self.QM_PC_gradient[i]=self.QMgradient_wo_linkatoms[qmcount]
                    qmcount+=1
                else:
                    #Pointcharge-gradient. Dipole-charge gradients are skipped (never reached)
                    self.QM_PC_gradient[i] = self.PCgradient[pccount]
                    pccount += 1
            assert qmcount == len(self.qmatoms)
            assert pccount == len(self.mmatoms)           


            #if self.printlevel >= 2:
            #    modules.module_coords.write_coords_all(self.PCgradient, self.mmatoms, indices=self.allatoms, file="PCgradient", description="PC gradient (au/Bohr):")


            #if self.printlevel >= 2:
            #    modules.module_coords.write_coords_all(self.QM_PC_gradient, self.elems, indices=self.allatoms, file="QM+PCgradient_before_linkatomproj", description="QM+PC gradient before linkatomproj (au/Bohr):")

            #LINKATOM FORCE PROJECTION
            # Add contribution to QM1 and MM1 contribution???
            if self.linkatoms==True:                
                #print("here")
                #print("linkatoms_dict: ", linkatoms_dict)
                #print("linkatoms_indices: ", linkatoms_indices)
                
                for pair in sorted(linkatoms_dict.keys()):
                    printdebug("pair: ", pair)
                    #Grabbing linkatom data
                    linkatomindex=linkatoms_indices.pop(0)
                    printdebug("linkatomindex:", linkatomindex)
                    Lgrad=self.QMgradient[linkatomindex]
                    printdebug("Lgrad:",Lgrad)
                    Lcoord=linkatoms_dict[pair]
                    printdebug("Lcoord:", Lcoord)
                    #Grabbing QMatom info
                    fullatomindex_qm=pair[0]
                    printdebug("fullatomindex_qm:", fullatomindex_qm)
                    printdebug("self.qmatoms:", self.qmatoms)
                    qmatomindex=fullindex_to_qmindex(fullatomindex_qm,self.qmatoms)
                    printdebug("qmatomindex:", qmatomindex)
                    Qcoord=self.qmcoords[qmatomindex]
                    printdebug("Qcoords: ", Qcoord)

                    Qgrad=self.QM_PC_gradient[fullatomindex_qm]
                    printdebug("Qgrad (full QM/MM grad)s:", Qgrad)
                    
                    #Grabbing MMatom info
                    fullatomindex_mm=pair[1]
                    printdebug("fullatomindex_mm:", fullatomindex_mm)
                    Mcoord=current_coords[fullatomindex_mm]
                    printdebug("Mcoord:", Mcoord)
                    
                    Mgrad=self.QM_PC_gradient[fullatomindex_mm]
                    printdebug("Mgrad (full QM/MM grad): ", Mgrad)
                    
                    #Now grabbed all components, calculating new projected gradient on QM atom and MM atom
                    newQgrad,newMgrad = linkatom_force_fix(Qcoord, Mcoord, Lcoord, Qgrad,Mgrad,Lgrad)
                    printdebug("newQgrad: ", newQgrad)
                    printdebug("newMgrad: ", newMgrad)
                    
                    #Updating full QM_PC_gradient (used to be QM/MM gradient)
                    #self.QM_MM_gradient[fullatomindex_qm] = newQgrad
                    #self.QM_MM_gradient[fullatomindex_mm] = newMgrad
                    self.QM_PC_gradient[fullatomindex_qm] = newQgrad
                    self.QM_PC_gradient[fullatomindex_mm] = newMgrad                    

        print_time_rel(CheckpointTime, modulename='QM/MM gradient prepare', moduleindex=2)
        CheckpointTime = time.time()


        #if self.printlevel >= 2:
        #    modules.module_coords.write_coords_all(self.QM_PC_gradient, self.elems, indices=self.allatoms, file="QM+PCgradient", description="QM+PC gradient (au/Bohr):")



        # MM THEORY
        if self.mm_theory_name == "NonBondedTheory":
            if self.printlevel >= 2:
                print("Running MM theory as part of QM/MM.")
                print("Using MM on full system. Charges for QM region  have to be set to zero ")
                #printdebug("Charges for full system is: ", self.charges)
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
                print("Using OpenMM theory as part of QM/MM.")
            if self.QMChargesZeroed==True:
                if self.printlevel >= 2:
                    print("Using MM on full system. Charges for QM region {} have been set to zero ".format(self.qmatoms))
            else:
                print("QMCharges have not been zeroed")
                ashexit()
            #printdebug("Charges for full system is: ", self.charges)
            #Todo: Need to make sure OpenMM skips QM-QM Lj interaction => Exclude
            #Todo: Need to have OpenMM skip frozen region interaction for speed  => => Exclude
            if Grad==True:
                print("QM/MM Grad is True")
                #Provide QM_PC_gradient to OpenMMTheory 
                if self.openmm_externalforce == True:
                    print("OpenMM externalforce is True")
                    #Take QM_PC gradient (link-atom projected) and provide to OpenMM external force
                    CheckpointTime = time.time()
                    self.mm_theory.update_custom_external_force(self.openmm_externalforceobject,self.QM_PC_gradient)

                    print_time_rel(CheckpointTime, modulename='QM/MM openMM: update custom external force', moduleindex=2)
                    if exit_after_customexternalforce_update==True:
                        print("OpenMM custom external force updated. Exit requested")
                        #This is used if OpenMM MD is handling forces and dynamics
                        return
                    #Calculate energy associated with external force so that we can subtract it later
                    self.extforce_energy=3*np.mean(sum(self.QM_PC_gradient*current_coords*1.88972612546))
                self.MMenergy, self.MMgradient= self.mm_theory.run(current_coords=current_coords, qmatoms=self.qmatoms, Grad=True)
            else:
                print("QM/MM Grad is false")
                self.MMenergy= self.mm_theory.run(current_coords=current_coords, qmatoms=self.qmatoms)
        else:
            self.MMenergy=0
        print_time_rel(CheckpointTime, modulename='MM step', moduleindex=2)
        CheckpointTime = time.time()


        #Final QM/MM Energy. Possible correction for OpenMM external force term
        self.QM_MM_energy= self.QMenergy+self.MMenergy-self.extforce_energy
        blankline()
        if self.printlevel >= 2:
            if self.embedding=="Elstat":
                print("Note: You are using electrostatic embedding. This means that the QM-energy is actually the polarized QM-energy")
                print("Note: MM energy also contains the QM-MM Lennard-Jones interaction\n")
            energywarning=""
            if self.TruncatedPC is True:
                if self.TruncatedPCflag is True:
                    print("Warning: Truncated PC approximation is active. This means that QM and QM/MM energies are approximate.")
                    energywarning="(approximate)"
                
            print("{:<20} {:>20.12f} {}".format("QM energy: ",self.QMenergy,energywarning))
            print("{:<20} {:>20.12f}".format("MM energy: ", self.MMenergy))
            print("{:<20} {:>20.12f} {}".format("QM/MM energy: ", self.QM_MM_energy,energywarning))
        blankline()



        #FINAL QM/MM GRADIENT ASSEMBLY
        if Grad == True:

            #If OpenMM external force method then QM/MM gradient is already complete
            if self.openmm_externalforce == True:
                self.QM_MM_gradient = self.MMgradient
            #Otherwise combine
            else:
                #Now assemble full QM/MM gradient
                assert len(self.QM_PC_gradient) == len(self.MMgradient)
                self.QM_MM_gradient=self.QM_PC_gradient+self.MMgradient


            if self.printlevel >=3:
                print("Printlevel >=3: Printing all gradients to disk")
                #print("QM gradient (au/Bohr):")
                #module_coords.print_coords_all(self.QMgradient, self.qmelems, self.qmatoms)
                modules.module_coords.write_coords_all(self.QMgradient_wo_linkatoms, self.qmelems, indices=self.qmatoms, file="QMgradient-without-linkatoms_{}".format(label), description="QM gradient w/o linkatoms {} (au/Bohr):".format(label))
                
                #Writing QM+Linkatoms gradient
                modules.module_coords.write_coords_all(self.QMgradient, self.qmelems+['L' for i in range(num_linkatoms)], indices=self.qmatoms+[0 for i in range(num_linkatoms)], file="QMgradient-with-linkatoms_{}".format(label), description="QM gradient with linkatoms {} (au/Bohr):".format(label))
                
                #blankline()
                #print("PC gradient (au/Bohr):")
                #module_coords.print_coords_all(self.PCgradient, self.mmelems, self.mmatoms)
                modules.module_coords.write_coords_all(self.PCgradient, self.mmelems, indices=self.mmatoms, file="PCgradient_{}".format(label), description="PC gradient {} (au/Bohr):".format(label))
                #blankline()
                #print("QM+PC gradient (au/Bohr):")
                #module_coords.print_coords_all(self.QM_PC_gradient, self.elems, self.allatoms)
                modules.module_coords.write_coords_all(self.QM_PC_gradient, self.elems, indices=self.allatoms, file="QM+PCgradient_{}".format(label), description="QM+PC gradient {} (au/Bohr):".format(label))
                #blankline()
                #print("MM gradient (au/Bohr):")
                #module_coords.print_coords_all(self.MMgradient, self.elems, self.allatoms)
                modules.module_coords.write_coords_all(self.MMgradient, self.elems, indices=self.allatoms, file="MMgradient_{}".format(label), description="MM gradient {} (au/Bohr):".format(label))
                #blankline()
                #print("Total QM/MM gradient (au/Bohr):")
                #print("")
                #module_coords.print_coords_all(self.QM_MM_gradient, self.elems,self.allatoms)
                modules.module_coords.write_coords_all(self.QM_MM_gradient, self.elems, indices=self.allatoms, file="QM_MMgradient_{}".format(label), description="QM/MM gradient {} (au/Bohr):".format(label))
            if self.printlevel >= 2:
                print(BC.WARNING,BC.BOLD,"------------ENDING QM/MM MODULE-------------",BC.END)
                print_time_rel(module_init_time, modulename='QM/MM run', moduleindex=2)
            return self.QM_MM_energy, self.QM_MM_gradient
        else:
            print_time_rel(module_init_time, modulename='QM/MM run', moduleindex=2)
            return self.QM_MM_energy











#Micro-iterative QM/MM Optimization
# NOTE: Not ready
#Wrapper around QM/MM run and geometric optimizer for performing microiterative QM/MM opt
# I think this is easiest
# Thiel: https://pubs.acs.org/doi/10.1021/ct600346p
#Look into new: https://pubs.acs.org/doi/pdf/10.1021/acs.jctc.6b00547

def microiter_QM_MM_OPT_v1(theory=None, fragment=None, chargemodel=None, qmregion=None, activeregion=None, bufferregion=None):
    
    ashexit()
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
    ashexit()
#xtb instead of charges
def microiter_QM_MM_OPT_v3(theory=None, fragment=None, maxiter=500, qmregion=None, activeregion=None, bufferregion=None,xtbdir=None,xtbmethod='GFN2-xTB', charge=None, mult=None):
    ashexit()
    #Make copy of orig theory
    orig_theory=copy.deepcopy(theory)
    # TODO: If BS-spinflipping, use Hsmult instead of regular mul6
    xtbtheory=xTBTheory(xtbdir=None, charge=charge, mult=mult, xtbmethod=xtbmethod, 
                        runmode='inputfile', numcores=1, printlevel=2)
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
        HLenergy,HLgrad=Singlepoint(theory=orig_theory,fragment=fragment,Grad=True, charge=charge, mult=mult)
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
            
        LLenergy,LLgrad=Singlepoint(theory=ll_theory,fragment=fragment,Grad=True, charge=charge, mult=mult)
        #Compare gradient, calculate G0 correction

        print("Now starting low-level theory QM/MM microtierative optimization")
        print("activeregion:", activeregion)
        print("ll_theory qm theory:", ll_theory.qm_theory)
        bla=geomeTRICOptimizer(theory=ll_theory,fragment=fragment, coordsystem='hdlc', maxiter=200, ActiveRegion=True, actatoms=activeregion, 
                            conv_criteria=loose_conv_criteria, charge=charge, mult=mult)
        print("Now starting finallevel theory QM/MM microtierative optimization")
        print("act_original:", act_original)
        print("orig_theory qm theory:", orig_theory.qm_theory)
        final=geomeTRICOptimizer(theory=orig_theory,fragment=fragment, coordsystem='hdlc', maxiter=200, ActiveRegion=True, actatoms=act_original, 
                            conv_criteria=final_conv_criteria, charge=charge, mult=mult)
        print("Micro-iterative QM/MM opt complete !")
    return final
    

#This projects the linkatom force onto the respective QM atom and MM atom
def linkatom_force_fix(Qcoord, Mcoord, Lcoord, Qgrad,Mgrad,Lgrad):
    printdebug("Qcoord:", Qcoord)
    printdebug("Mcoord:", Mcoord)
    printdebug("Lcoord:", Lcoord)
    #QM1-L and QM1-MM1 distances
    QLdistance=modules.module_coords.distance(Qcoord,Lcoord)
    printdebug("QLdistance:", QLdistance)
    MQdistance=modules.module_coords.distance(Mcoord,Qcoord)
    printdebug("MQdistance:", MQdistance)
    #B and C: a 3x3 arrays
    B=np.zeros([3,3])
    C=np.zeros([3,3])
    for i in range(0,3):
        for j in range(0,3):
            B[i,j]=-1*QLdistance*(Mcoord[i]-Qcoord[i])*(Mcoord[j]-Qcoord[j]) / (MQdistance*MQdistance*MQdistance)
    for i in range(0,3):
        B[i,i] = B[i,i] + QLdistance / MQdistance
    for i in range(0,3):
        for j in range(0,3):
            C[i,j]= -1 * B[i,j]
    for i in range(0,3):
        C[i,i] = C[i,i] + 1.0                

    #Multiplying C matrix with Linkatom gradient
    #temp
    g_x=C[0,0]*Lgrad[0]+C[0,1]*Lgrad[1]+C[0,2]*Lgrad[2]
    g_y=C[1,0]*Lgrad[0]+C[1,1]*Lgrad[1]+C[1,2]*Lgrad[2]
    g_z=C[2,0]*Lgrad[0]+C[2,1]*Lgrad[1]+C[2,2]*Lgrad[2]
    
    printdebug("g_x:", g_x)
    printdebug("g_y:", g_y)
    printdebug("g_z:", g_z)
    
    #Multiplying B matrix with Linkatom gradient
    gg_x=B[0,0]*Lgrad[0]+B[0,1]*Lgrad[1]+B[0,2]*Lgrad[2]
    gg_y=B[1,0]*Lgrad[0]+B[1,1]*Lgrad[1]+B[1,2]*Lgrad[2]
    gg_z=B[2,0]*Lgrad[0]+B[2,1]*Lgrad[1]+B[2,2]*Lgrad[2]                    
    
    printdebug("gg_x:", gg_x)
    printdebug("gg_y:", gg_y)
    printdebug("gg_z:", gg_z)
    #QM atom gradient
    printdebug("Qgrad before:", Qgrad)
    printdebug("Lgrad:", Lgrad)
    printdebug("C: ", C)
    printdebug("B:", B)
    #Multiply grad by C-diagonal
    #Qgrad[0] = Qgrad[0]*C[0][0]
    #Qgrad[1] = Qgrad[1]*C[1][1]
    #Qgrad[2] = Qgrad[2]*C[2][2]
    Qgrad[0]=Qgrad[0]+g_x
    Qgrad[1]=Qgrad[1]+g_y
    Qgrad[2]=Qgrad[2]+g_z
    printdebug("Qgrad after:", Qgrad)
    #MM atom gradient
    printdebug("Mgrad before", Mgrad)
    #Mgrad[0] = Mgrad[0]*B[0][0]
    #Mgrad[1] = Mgrad[1]*B[1][1]
    #Mgrad[2] = Mgrad[2]*B[2][2]
    Mgrad[0]=Mgrad[0]+gg_x
    Mgrad[1]=Mgrad[1]+gg_y
    Mgrad[2]=Mgrad[2]+gg_z                    
    printdebug("Mgrad after:", Mgrad)
    
    return Qgrad,Mgrad

def fullindex_to_qmindex(fullindex,qmatoms):
    qmindex=qmatoms.index(fullindex)
    return qmindex


#Grab resid column from PDB-fil
# NOTE: Problem: what if we have repeating sequences of resids, additional chains or segments ?
#TODO: this is 1-based indexing. Switch to 0-based indexing??
def grab_resids_from_pdbfile(pdbfile):
    resids=[]
    with open(pdbfile) as f:
        for line in f:
            if 'ATOM' in line or 'HETATM' in line:
                #Based on: https://cupnet.net/pdb-format/
                resid_part=int(line[22:26].replace(" ",""))
                resids.append(resid_part)
    return resids

#Define active region based on radius from an origin atom.
#Requires fragment (for coordinates) and resids list inside OpenMMTheory object
#TODO: Also allow PDBfile to grab resid information from?? Prettier since we don't have to create an OpenMMTheory object
def actregiondefine(pdbfile=None, mmtheory=None, fragment=None, radius=None, originatom=None):
    """ActRegionDefine function

    Args:
        mmtheory ([OpenMMTheory]): OpenMMTheory object. Defaults to None.
        fragment ([Fragment]): ASH Fragment. Defaults to None.
        radius ([int]): Radius (in Angstrom). Defaults to None.
        originatom ([int]): Origin atom for radius. Defaults to None.

    Returns:
        [type]: [description]
    """
    print_line_with_mainheader("ActregionDefine")

    #Checking if proper information has been provided
    if radius == None or originatom == None:
        print("actregiondefine requires radius and originatom keyword arguments")
        ashexit()
    if pdbfile == None and fragment == None:
        print("actregiondefine requires either fragment or pdbfile arguments (for coordinates)")
        ashexit()
    if pdbfile == None and mmtheory == None:
        print("actregiondefine requires either pdbfile or mmtheory arguments (for residue topology information)")
        ashexit()
    #Creating fragment from pdbfile 
    if fragment == None:
        print("No ASH fragment provided. Creating ASH fragment from PDBfile")
        fragment = Fragment(pdbfile=pdbfile, printlevel=1)

    print("Radius:", radius)
    print("Origin atom: {} ({})".format(originatom,fragment.elems[originatom]))
    print("Will find all atoms within {} Å from atom: {} ({})".format(radius,originatom,fragment.elems[originatom]))
    print("Will select all whole residues within region and export list")
    if mmtheory != None:
        if mmtheory.__class__.__name__ == "NonBondedTheory":
            print("MMtheory: NonBondedTheory currently not supported.")
            ashexit()
        if not mmtheory.resids :
            print(BC.FAIL,"mmtheory.resids list is empty! Something wrong with OpenMMTheory setup. Exiting",BC.END)
            ashexit()
        #Defining list of residue from OpenMMTheory object 
        resids=mmtheory.resids
    else:
        #No mmtheory but PDB file should have been provided
        #Defining resids list from PDB-file
        #NOTE: Call grab_resids_from_pdbfile
        resids = grab_resids_from_pdbfile()
        print("Not ready yet")
        ashexit()
        ashexit()

    origincoords=fragment.coords[originatom]
    act_indices=[]
    
    for index,allc in enumerate(fragment.coords):
        #print("index:", index)
        #print("allc:", allc)
        dist=modules.module_coords.distance(origincoords,allc)
        if dist < radius:
            #print("DIST!!")
            #print("index:", index)
            #print("allc:", allc)
            #Get residue ID for this atom index
            resid_value=resids[index]
            #print("resid_value:", resid_value)
            #Get all residue members (atom indices)
            resid_members = [i for i, x in enumerate(resids) if x==resid_value]
            #print("resid_members:", resid_members)
            #Adding to act_indices list unless already added
            for k in resid_members:
                if k not in act_indices:
                    act_indices.append(k)

    #Only unique and sorting:
    act_indices = np.unique(act_indices).tolist()

    #Print indices to output
    #Print indices to disk as file
    writelisttofile(act_indices, "active_atoms")
    #Print information on how to use
    print("Active region size:", len(act_indices))
    print("Active-region indices written to file: active_atoms")
    print("The active_atoms list  can be read-into Python script like this:	 actatoms = read_intlist_from_file(\"active_atoms\")")
    #Print XYZ file with active region shown
    modules.module_coords.write_XYZ_for_atoms(fragment.coords,fragment.elems, act_indices, "ActiveRegion")
    print("Wrote Active region XYZfile: ActiveRegion.xyz  (inspect with visualization program)")
    return act_indices


