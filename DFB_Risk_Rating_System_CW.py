import arcpy
print("Starting...")
print()
arcpy.env.overwriteOutput = True

# *****RESET PATH to UNZIPPED FOLDER HERE*******
path = "D:\FinalZipped2"
# Set local variables
gdb_name = "\FinalProject2.gdb"
workspace = path + gdb_name

# Execute CreateFileGDB
gdb = arcpy.CreateFileGDB_management(path, gdb_name)
print("File gdb created...")
print()

#Define workspace
arcpy.env.workspace = workspace

#Create feature classes from shapefiles
wsaboundary = arcpy.conversion.FeatureClassToFeatureClass(path + "\GVWSA_Boundary.shp", gdb, "wsaboundary")
BC_VRI = arcpy.conversion.FeatureClassToFeatureClass(path + "\BC_VRI.shp", gdb, "BC_VRI")
WSA_Disease_Insect = arcpy.conversion.FeatureClassToFeatureClass(path + "\WSA_Disease_Insect.shp", gdb, "WSA_Disease_Insect")
print("Feature classes created...")
print()

#Intersect watershed boundary with BC_VRI to only use forest stands in the Greater Victoria Water Supply Area
WSA_VRI = arcpy.analysis.Intersect([BC_VRI, wsaboundary], "WSA_VRI")
print("WSA_VRI created...")
print()

#Select only DFB Stands from WSA_Insect_Disease dataset
DFBStands = arcpy.management.SelectLayerByAttribute("WSA_Disease_Insect", "NEW_SELECTION","FHF2 = 'IBD' Or FHF2 = 'DRL/IBD' Or FHF2 = 'ND/IBD' Or FHF1 = 'IBD' Or FHF1 = 'IBD/DRA/D*'")

#Copy DFBStands to new feature class
DFBStands = arcpy.management.CopyFeatures(DFBStands, path + gdb_name + "/DFBStands")
print("DFBStands created...")
print()

#Determine nearest DFB stand to each forest stand in WSA_VRI
arcpy.Near_analysis(WSA_VRI, DFBStands)
print("Near function complete...")
print()

#Add rating system classification value fields to WSA_VRI dataset (Suscpetibility - Age, Diameter, Purity) (Beetle Population Factors - Infested, number of trees) (Risk- Risk value)
newfields = ["Age", "Diameter", "Stand_Purity","Susceptibility_Factor", "Infested", "Number_of_Trees","Beetle_Pop_Factor", "Risk"]


for field in newfields:
    arcpy.AddField_management(WSA_VRI, field, "FLOAT")
print("New fields added...")
print()

#Populate new fields based susceptibility and beetle population factor and risk calculations from forest stand characteristics in WSA_VRI attribute table
'''Fields used to calculate each variable classification
Susceptibility:
Age - SPEC_CD_1 and PROJ_AGE_1 if SPEC_CD_1 is douglas fir. SPEC_CD_2 and PROJ_AGE_2 if SPEC_CD_2 is douglas fir.
Diameter - Q_DIAM_175 for quadratic mean stand diameter (breast height) based on the 17.5 cm utilization level.
Stand Purity - BASAL_AREA for average basal area of stand multiplied by SPECIES_PCT_1 if SPEC_CD_1 is douglas fir or SPECIES_PCT_2 if SPEC_CD_2 is douglas fir
Susceptibility_factor - product of multiplying age, diameter, and stand purity values (possible values = 0-100)
**If any data is missing for these fields they are deemed NoData and are not included.

Beetle Population Factors:
Infested = If NEAR_DIST < 1000 m then this field equals 1.0 (DFBStands only contains stands of trees infested) otherwise go no further and BPF equals 0.1
Number of trees = Using NEAR_FID in nested search cursor retrieve number of trees infected from DFBStands attribute table.
Beetle_pop_factor - product of multiplying Infested and number of trees (possible values = 0-1)

Risk - Susceptibility multiplied by beetle population factor (0-100)
'''
#Fields to search
fields = ["Q_DIAM_175", "BASAL_AREA", "SPEC_CD_1", "SPEC_PCT_1", "SPEC_CD_2", "SPEC_PCT_2","SPEC_CD_3", "SPEC_PCT_3", "SPEC_CD_4", "SPEC_PCT_4", "SPEC_CD_5", "SPEC_PCT_6", "PROJ_AGE_1", "PROJ_AGE_2", "NEAR_FID", "NEAR_DIST", "Age", "Diameter", "Stand_Purity", "Susceptibility_Factor", "Infested", "Number_of_Trees", "Beetle_Pop_Factor", "Risk", "OBJECTID_1"]

count = 0
nodata = 0

with arcpy.da.UpdateCursor(WSA_VRI, (fields)) as cursor:
    for stand in cursor:
        
        #Age
        if stand[2] == "FD" or stand[2] == "FDC":
            age = int(stand[13])
            #if age == 0:
                #age = "NoData"
            if age <80:
                age = 0.3
            elif age >= 80 and age < 120:
                age = 0.6
            elif age >= 120 and age < 150:
                age = 0.8
            elif age >=150:
                age = 1.
        elif stand[4] == "FD" or stand[4] == "FDC":
            age = int(stand[14])
            #if age == 0:
                #age = "NoData"
            if age <80:
                age = 0.3
            elif age >= 80 and age < 120:
                age = 0.6
            elif age >= 120 and age < 150:
                age = 0.8
            elif age >=150:
                age = 1.0
        stand[16] = age

        #Diameter
        dbh = float(stand[0])
        #if dbh == 0:
            #dbh = "NoData"
        if dbh <29:
            dbh = 0.3
        elif dbh >= 29 and dbh < 40:
            dbh = 0.8
        elif dbh >= 40:
            dbh = 1.0
        stand[17] = dbh

        #Stand Purity
        if stand[2] == "FD" or stand[2] == "FDC":
            purity = int(stand[3])
            
        elif stand[4] == "FD" or stand[4] == "FDC":
            purity = int(stand[5])
        elif stand[6] == "FD" or stand[6] == "FDC":
            purity = int(stand[7])
        elif stand[8] == "FD" or stand[8] == "FDC":
            purity = int(stand[9])
        elif stand[10] == "FD" or stand[10] == "FDC":
            purity = int(stand[11])
        stand[18] = purity

        #Susceptibility factor
        if age == 0 or dbh == 0 or purity == 0:
            nodata += 1
            susceptibility = 0
        else:
            susceptibility = age * dbh * purity
            stand[19] = float(susceptibility)


        #Beetle Population Factor Section
        #Infested (1 if NEAR_DIST < 1000m, 0.1 if not)
        #If infested = 1.0, determine number of trees infected using NEAR_FID in search cursor
        if int(stand[15]) <= 1000:
            stand[20] = 1.0
            ID = stand[14]
            whereexpr = "OBJECTID_12 = %s"% ID
            fields = ["OBJECTID_12","NumTrees"]

            with arcpy.da.SearchCursor(DFBStands, (fields), whereexpr) as DFB:
                for infected in DFB:
                    numtrees = int(infected[1])
            if numtrees >= 20:
                numtrees = 1.0
                stand[21] = numtrees
            elif numtrees >=5 and numtrees <20:
                numtrees = 0.8
                stand[21] = numtrees
            elif numtrees <5:
                numtrees = 0.6
                stand[21] = numtrees
            #Calculate beetle population factor (Infested * number of trees
            beetlepopfactor = 1.0 * numtrees
            stand[22] = beetlepopfactor

        elif int(stand[15]) > 1000:
            stand[20] = 1.0
            numtrees = 0
            stand[21] = numtrees
            beetlepopfactor = 0.1  
            stand[22] = beetlepopfactor
        #print("stand number is:", stand[24], "distance to infected stand is:", stand[15],"DFB stand FID is:", stand[14], "number of infected trees within 1 km is", numtrees)
                     
        # Calculate risk factor (Susceptibility factor * Beetle population factor) 
        risk = susceptibility * beetlepopfactor
        if risk >0:
            stand[23] = risk
        count += 1
        cursor.updateRow(stand)
        

    print(nodata, "out of", count,"stands have missing data")

