import numpy as np
#Psi4 interface.
# Inputfile version.
# Todo: replace with python-interface version

#create inputfile

#run Psi4 input


#check if Psi4 finished

#grab energy from output

def grabPsi4EandG(outfile, numatoms, Grad):
    gradient = np.zeros((numatoms, 3))
    row=0
    print("here")
    with open(outfile) as ofile:
        for line in ofile:
            if '    Total Energy =' in line:
                energy = float(line.split()[-1])

            if Grad == True:
                print("Psi4 gradient grab not tested yet")
                if '  -Total Gradient:' in line:
                    gradgrab = True
                if gradgrab==True:
                    if len(line) < 1:
                        gradgrab=False
                    if '--' not in line and 'Atom' not in line:
                        val=line.split()
                        gradient[row] = [float(val[1]),float(val[2]),float(val[3])]
                        row+=1

    if Grad==True:
        return energy, gradient
    else:
        return energy