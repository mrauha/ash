#Some Julia functions
__precompile__()

module Juliafunctions
#using PyCall


#Untested
function LJcoulombchargev1a(charges, coords, epsij, sigmaij, connectivity=nothing)
    """LJ + Coulomb function"""
    ang2bohr = 1.88972612546
    coords_b=coords*ang2bohr
    num=length(charges)
    #Pre-compute Euclidean distance array
    #Does not save time when we need to other r quantities
    #@time dists=distance(coords_b,coords_b)
    coulenergy=0.0
    V_LJ=0.0
    coulgradient = zeros(size(coords_b)[1], 3)
    for j=1:num
        for i=j+1:num
            sigma=sigmaij[i,j]
            eps=epsij[i,j]
            #d=dists[i,j]
            #Arrays are surprisingly slow.
            rij_x = coords_b[j,1] - coords_b[i,1]
            rij_y = coords_b[j,2] - coords_b[i,2]
            rij_z = coords_b[j,3] - coords_b[i,3]
            r = rij_x*rij_x+rij_y*rij_y+rij_z*rij_z
            d = sqrt(r)
            ri=1/r
            ri3=ri*ri*ri
            coulenergy+=charges[i]*charges[j]/(d)
            d_ang = d / ang2bohr
            V_LJ+=4*eps*((sigma/d_ang)^12-(sigma/d_ang)^6)
            LJgrad_const=(24*eps*((sigma/d_ang)^6-2*(sigma/d_ang)^12))*(1/(d_ang^2))
            Gij_x=-1*charges[i]*charges[j]*sqrt(ri3)*rij_x*LJgrad_const
            Gij_y=-1*charges[i]*charges[j]*sqrt(ri3)*rij_y*LJgrad_const
            Gij_z=-1*charges[i]*charges[j]*sqrt(ri3)*rij_z*LJgrad_const

            coulgradient[j,1] +=  Gij_x
            coulgradient[j,2] +=  Gij_y
            coulgradient[j,3] +=  Gij_z
            coulgradient[i,1] -=  Gij_x
            coulgradient[i,2] -=  Gij_y
            coulgradient[i,3] -=  Gij_z
        end
    end
    E = coulenergy + V_LJ
    #G = coulgradient
    return E,coulgradient
end




#TODO functions:
#Rewrite connectivity in Julia here
#Maybe some molcrys cluster-create,delete steps??

#Calculate the sigmaij and epsij arrays
#Key things for speed:
# i:numatoms, j=i+1:numatoms
# Using fast dict-lookup, simple double-if condition for qmatoms (was slowing things down a lot with all thing)
# Avoided dict-lookup for both key-existence and value
#https://stackoverflow.com/questions/58170034/how-do-i-check-if-a-dictionary-has-a-key-in-it-in-julia
#frozenatoms option is slow
function pairpot_full(numatoms,atomtypes,LJpydict,qmatoms)
    #Updating atom indices from 0 to 1 syntax
    qmatoms=[i+1 for i in qmatoms]
    #frozenatoms=[i+1 for i in frozenatoms]
    #Convert Python dict to Julia dict with correct types
    LJdict_jul=convert(Dict{Tuple{String,String},Array{Float64,1}}, LJpydict)
    #println(typeof(LJdict_jul))
    sigmaij=zeros(numatoms, numatoms)
    epsij=zeros(numatoms, numatoms)

for i in 1:numatoms
    for j in i+1:numatoms
        if i in qmatoms && j in qmatoms
            continue
        else
           #Checking if dict contains key, return value if so, otherwise nothing
           v = get(LJdict_jul, (atomtypes[i],atomtypes[j]), nothing)
           if v !== nothing
             sigmaij[i, j] = v[1]
             epsij[i, j] =  v[2]
           else
             v = get(LJdict_jul, (atomtypes[j],atomtypes[i]), nothing)
             if v !== nothing
               sigmaij[i, j] = v[1]
               epsij[i, j] =  v[2]
             end
           end
	    end
    end
end
return sigmaij,epsij
end

#Modified pairpot that only does active atoms
#Fills whole symmetric array just in case,i .e. ij and ji
function pairpot_active(numatoms,atomtypes,LJpydict,qmatoms,actatoms)
	#println("inside pairpot_active")
    #Updating atom indices from 0 to 1 syntax
    qmatoms=[i+1 for i in qmatoms]
    actatoms=[i+1 for i in actatoms]
    #Convert Python dict to Julia dict with correct types
    LJdict_jul=convert(Dict{Tuple{String,String},Array{Float64,1}}, LJpydict)
    #println(typeof(LJdict_jul))
    sigmaij=zeros(numatoms, numatoms)
    epsij=zeros(numatoms, numatoms)
	#println("-----")
	#println("qmatoms : $qmatoms")
	#println("actatoms: $actatoms")
	#println("-----")
	#println("numatoms: $numatoms")
	for i in 1:numatoms
		for j in actatoms
			#println("i is $i and j is $j")
			#println("count_i is $count_i")
			#println("atomtypes[i]", atomtypes[i])
			#println("atomtypes[j]", atomtypes[j])
			if i in qmatoms && j in qmatoms
				continue
			else
				#println("else")
			   #Checking if dict contains key, return value if so, otherwise nothing
			   #Todo: what if we have v be value or 0 instead of nothing. Can then skip the if statement?
			   v = get(LJdict_jul, (atomtypes[i],atomtypes[j]), nothing)
			   if v !== nothing
				 sigmaij[i, j] = v[1]
				 epsij[i, j] =  v[2]
				 sigmaij[j, i] = v[1]
				 epsij[j, i] =  v[2]
				#println("here")
			   else
				 v = get(LJdict_jul, (atomtypes[j],atomtypes[i]), nothing)
				 if v !== nothing
				   sigmaij[i, j] = v[1]
				   epsij[i, j] =  v[2]
				   sigmaij[j, i] = v[1]
				   epsij[j, i] =  v[2]
				 end
			   end
			end
		end
	end
	return sigmaij,epsij
	end

#Distance for 2D arrays of coords
function distance(x::Array{Float64, 2}, y::Array{Float64, 2})
    nx = size(x, 1)
    ny = size(y, 1)
    r=zeros(nx,ny)
        for j = 1:ny
            @fastmath for i = 1:nx
                @inbounds dx = y[j, 1] - x[i, 1]
                @inbounds dy = y[j, 2] - x[i, 2]
                @inbounds dz = y[j, 3] - x[i, 3]
                rSq = dx*dx + dy*dy + dz*dz
                @inbounds r[i, j] = sqrt(rSq)
            end
        end
    return r
end

#function get_connected_atoms_julia(coords, elems,eldict_covrad, scale,tol, atomindex):
#    eldict_covrad_jul=convert(Dict{String,Float64}, eldict_covrad)
#    connatoms = Array(Int, 0)
#    coords_ref=coords[atomindex]
#    elem_ref=elems[atomindex]

#    for (i,c) in enumerate(coords)
#        if distance(coords_ref,c) < scale*(eldict_covrad_jul[elems[i]]+eldict_covrad_jul[elem_ref]) + tol
#            push!(connatoms, i)
#TODO: remove atomindex from connatoms
#    return connatoms
#end


#Python-ish version
#function get_connected_atoms_julia_vector(coords, elems,eldict_covrad, scale,tol, atomindex)
#    eldict_covrad_jul=convert(Dict{String,Float64}, eldict_covrad)

    #Pre-compute Euclidean distance array
#    dists=distance(coords,coords)

    #Getting all thresholds as list via list comprehension.
#    el_covrad_ref=eldict_covrad[elems[atomindex]]
    # TODO: Slowest part but hard to make faster
#    thresholds=np.array([eldict_covrad[elems[i]] for i in range(len(elems))])
    #Numpy addition and multiplication done on whole array
#    thresholds=thresholds+el_covrad_ref
#    thresholds=thresholds*scale
#    thresholds=thresholds+tol
    #Old slow way
    #thresholds=np.array([threshold_conn(elems[i], elem_ref,scale,tol) for i in range(len(elems))])
    #Getting difference of distances and thresholds
#    diff=distances-thresholds

#    connatoms = []
    #Getting connatoms by finding indices of diff with negative values (i.e. where distance is smaller than threshold)
#    connatoms=np.where(diff<0)[0].tolist()
#    return connatoms
#end



#End of Julia module
end