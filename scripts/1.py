import csv

# WAY MAKER GENERAL OPC (ONE PERSON CORPORATION)
# Note: OPCs only have one shareholder/owner by law

data = [
    ["Type", "Name", "Position/Role", "Nationality", "Gender", "Shares Owned", "Share Type", "Amount (PhP)", "% Ownership", "TIN"],
    # Single Stockholder (OPC structure)
    ["Stockholder", "ERICKA D. GALANG", "Sole Stockholder & President", "Filipino", "F", "All", "COMMON", "Amount TBD", "100%", ""],
    # Officers
    ["Officer", "ERICKA D. GALANG", "President", "Filipino", "F", "All", "COMMON", "Amount TBD", "100%", ""],
    ["Officer", "NOMINEE: [Name in AOI]", "Corporate Secretary & Treasurer", "Filipino", "", "0", "NONE", "0.00", "0%", ""],
]

# Note: Need to extract exact capital structure from 19K character AOI file
print("⏳ Processing Way Maker General OPC...")
print("This is a ONE PERSON CORPORATION (OPC)")
print("OPCs are 100% owned by a single individual by law")
print("Owner: ERICKA D. GALANG")
print("")
print("Extracting full details from AOI file...")

