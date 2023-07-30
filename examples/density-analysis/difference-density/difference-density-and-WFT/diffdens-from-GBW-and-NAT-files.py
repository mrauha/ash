from ash import *
import glob
import os

##############################################################
# Difference density generation script via ORCA orbitalfiles
##############################################################
#Defines a reference file and then finds all other ORCA .gbw (for SCF) or nat files (natural orbitals from WFT)
#Molden files are created, Multiwfn is called on to create density files (Cube files)
#Difference-densities generated by subtraction
##############################################################


#Reference for Difference density cubes
reference="HF.gbw"

print("Using reference orbitals from file:", reference)

#Read all GBW and NAT files into list
print("Now searching dir for .gbw and .nat files")
gbwfiles=glob.glob('*.gbw')
natfiles=glob.glob('*nat')
moldenfiles=glob.glob('*.molden')
print("Found gbwfiles", gbwfiles)
print("Found natfiles:", natfiles)
orbfiles=gbwfiles+natfiles
print("Total orbfiles:", orbfiles)


moldenfiles=[]
cubefiles=[]

for gfile in orbfiles:
    gfile_base=str(os.path.splitext(gfile)[0])
    #Check if Cube-file exits already
    if os.path.exists(gfile_base+".molden.input_mwfn.cube"):
        print("Orbital file:", gfile)
        print("Cube-file exists already:", gfile_base+".molden.input_mwfn.cube")
        cubefiles.append(gfile_base+".molden.input_mwfn.cube")
    else:
        # Create Molden files from GBW
        mfile = make_molden_file_ORCA(gfile)
        moldenfiles.append(mfile)
        #Create Cube files via Multiwfn
        cube=multiwfn_run(mfile, option='density', grid=3)
        cubefiles.append(cube)

assert len(cubefiles) == len(moldenfiles)
print("\nNow calculating difference density w.r.t.:", reference)

#Which reference to use
ref_index=orbfiles.index(reference)
ref_cubefile=cubefiles[ref_index]
ref_cube_data=read_cube(ref_cubefile)
ref_label=reference.replace(".gbw", "").replace(".nat", "")

#Looping over cubefiles and taking difference w.r.t. reference
for index,cubefile in enumerate(cubefiles):
    label=orbfiles[index].replace(".gbw","").replace("nat", "")
    #Read Cubefiles into memory
    cube_d=read_cube(cubefile)
    #Taking diff
    write_cube_diff(ref_cube_data, cube_d, f"{ref_label}_{label}_diff_density")
