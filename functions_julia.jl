#Some Julia functions
__precompile__()

module Juliafunctions
#using PyCall

function hellofromjulia()
println("Hello from Julia")
end

function juliatest(list)
println("Inside juliatest")
println("list is : $list")
var=5.4
return var
end

#Calculate the sigmaij and epsij arrays

#Dict version
function pairpot3(numatoms,atomtypes,LJpydict,qmatoms)
    #Convert Python dict to Julia dict with correct types
    LJdict_jul=convert(Dict{Tuple{String,String},Array{Float64,1}}, LJpydict)
    #println(typeof(LJdict_jul))
    sigmaij=zeros(numatoms, numatoms)
    epsij=zeros(numatoms, numatoms)
for i in 1:numatoms
    for j in 1:numatoms
        for (ljpot_types, ljpot_values) in LJdict_jul
            #Skipping if i-j pair in qmatoms list. I.e. not doing QM-QM LJ calc.
            if all(x in qmatoms for x in [i, j])
                #print("Skipping i-j pair", i,j, " as these are QM atoms")
                continue
            end
            if atomtypes[i] == ljpot_types[1] && atomtypes[j] == ljpot_types[2]
                sigmaij[i, j] = ljpot_values[1]
                epsij[i, j] = ljpot_values[2]
            elseif atomtypes[j] == ljpot_types[1] && atomtypes[i] == ljpot_types[2]
                sigmaij[i, j] = ljpot_values[1]
                epsij[i, j] = ljpot_values[2]
            end
        end
    end
end
return sigmaij,epsij
end





#End of Julia module
end