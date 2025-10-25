# EOGO Corruption Risk Analysis
## Based on: "Corruption risk and political dynasties: exploring the links using public procurement data in the Philippines"

**Authors:** Daniel Bruno Davis, Ronald U. Mendoza, Jurel K. Yap  
**Source:** Economics of Governance (2023)  
**DOI:** https://doi.org/10.1007/s10101-023-00306-4

---

## Overview

This analysis framework measures corruption risk in Philippine public procurement using statistical techniques to synthesize contract quality data into a **Corruption Risk Indicator (CRI)**.

**Key Finding:** Political dynasties (measured by Political HHI and dynasty size) are significantly linked to HIGHER corruption risk in public procurement.

---

## Corruption Risk Indicator (CRI)

### Methodology
- Uses **Item Response Theory (IRT)** model
- Synthesizes 9 contract characteristics into a normalized score
- CRI = 0: Average corruption risk
- CRI < 0: Lower corruption risk
- CRI > 0: Higher corruption risk

### The 9 Red Flag Factors

#### 1. **Procurement Mode**
- **Measure:** Whether contract used open public bidding
- **Red Flag:** Non-competitive procurement (negotiated, shopping, etc.)
- **Our Data:** ✅ `philgeps.contracts.business_category`
- **Note:** Open bidding = lower risk; Direct award = higher risk

#### 2. **Time to Close**
- **Measure:** Days from publication to closing date
- **Standard:** Should be 14 days minimum (per GPRA)
- **Red Flag:** < 14 days (insufficient time for competition)
- **Our Data:** ❌ Missing - Need `publication_date` and `closing_date`

#### 3. **Approved Budget**
- **Measure:** Contract amount (divided into 20 tranches)
- **Red Flag:** Unusually high/low amounts for project type
- **Our Data:** ✅ `philgeps.contracts.contract_amount`

#### 4. **Notice Status**
- **Measure:** Was contract entered into PhilGEPS AFTER award? (Binary)
- **Red Flag:** Late entry = potential attempt to hide or avoid scrutiny
- **GPRA Requirement:** Must be entered BEFORE award
- **Our Data:** ❌ Missing - Need `entry_date` vs `award_date`

#### 5. **Classification**
- **Measure:** Type of service/project/good
- **Red Flag:** Certain categories more prone to corruption
- **Our Data:** ✅ `philgeps.contracts.business_category`

#### 6. **Effective Date to End Date**
- **Measure:** Contract duration (days)
- **Red Flag:** Unusually short/long contract periods
- **Our Data:** ❌ Missing - Need `contract_end_date` (only have `award_date`)

#### 7. **Contract Difference**
- **Measure:** Difference between approved budget and final contract amount
- **Formula:** `(Final Amount - Initial Estimate) / Initial Estimate`
- **Red Flag:** Large deviations = potential cost inflation
- **Our Data:** ❌ Missing - Need `initial_estimated_price`

#### 8-9. **Additional Factors**
- Not fully specified in the excerpt
- Likely related to: number of bidders, contract amendments, procurement method variations

---

## Political Dynasty Indicators

### 1. Political HHI (Herfindahl–Hirschman Index)

**Formula:**
```
PoliticalHHI = f₁² + f₂² + ... + fₙ²
```

Where:
- `fᵢ` = "market share" of each surname (political clan) in the province
- `fᵢ` = (# of positions held by clan / total positions) × 100
- Expressed as whole number (e.g., 50% = 50)

**Example:**
- 1 family with 50% of positions: HHI = 50² = 2,500
- 10 families with 10% each: HHI = 10×(10²) = 1,000
- Higher HHI = more concentration

**Our Data:** ❌ Missing - Need elected officials dataset with:
- Surname
- Position (Governor, Mayor, Congressman, etc.)
- Province
- Term/Year

**Result:** Each unit increase in Political HHI → 0.002 SD increase in CRI (significant at 5% level)

---

### 2. Size of Largest Dynasty

**Definition:** Number of elected officials from the largest political clan in a province (minimum 2 people sharing a surname)

**Our Data:** ❌ Missing - Same dataset needed as Political HHI

**Result:** Each unit increase in largest dynasty size → 0.018-0.020 SD increase in CRI (significant at 1% level)

---

### 3. GCM Link (Governor-Congressman-Mayor Link)

**Definition:** Dummy variable = 1 if elected governor has at least 1 mayor AND 1 congressman with same surname in the province in same term

**Our Data:** ❌ Missing - Same dataset needed

**Result:** NOT significantly linked to CRI in this study

---

## Control Variables

### We Can Calculate/Obtain:

1. **Distance from Manila**
   - ✅ Can calculate from province coordinates
   - Expected: Positive link (farther = more corruption risk)

2. **Population**
   - ✅ Can get from PSA
   - Result: Negative link (smaller provinces = more corruption risk)

3. **Number of Seats**
   - ✅ Can calculate (Governor + Vice-Governor + Board Members + Mayors + Congressmen per province)
   - Controls for government size

4. **Total Contracts**
   - ✅ We have: Count of `philgeps.contracts` per province
   - Controls for data availability

### Need External Data:

5. **IRA (Internal Revenue Allotment Dependency Ratio)**
   - ❌ Need: Department of Finance data
   - Measures fiscal decentralization
   - Expected: Positive link (more IRA = more rent-seeking)

6. **Povertyp (Poverty Incidence)**
   - ❌ Need: PSA triennial poverty data
   - Expected: Positive link (more poverty = more corruption risk)

7. **EthFracp (Ethnolinguistic Fractionalization)**
   - ❌ Need: PSA 2010 census ethnicity data
   - Formula: `EthFracp = 1 - Σsᵢ²` where sᵢ = population share of ethnic group
   - Expected: Positive link (more fractionalization = more corruption risk)

---

## Regression Model

### Model A (Cross-sectional):
```
Cp = β₁Sp + β₂Sp₋₃ + β₃Tp + β₄Up + β₅Vp + β₆log(Wp) + β₇log(Xp) + β₈log(Yp) + β₉Zp + εp
```

Where:
- `Cp` = CRI for province p
- `Sp` = Political HHI
- `Sp₋₃` = Political HHI lagged (previous term)
- `Tp` = Size of largest dynasty
- `Up` = GCM Link
- `Vp` = IRA dependency ratio
- `Wp` = Poverty incidence
- `Xp` = Population
- `Yp` = Distance from Manila
- `Zp` = Ethnolinguistic fractionalization

### Model B (Panel with time fixed effects):
```
Cp,t = β₁Sp,t + β₂Sp,t₋₃ + β₃Tp,t + β₄Up,t + β₇log(Xp,t) + β₈log(Yp,t) + ωt + εp,t
```

---

## Data Availability Assessment

### ✅ **What We Currently Have:**

1. **PhilGEPS Contracts** (`philgeps.contracts`)
   - Contract amount
   - Award date
   - Business category
   - Awardee name
   - Organization name
   - Area of delivery (province)
   - Award status

2. **Geographic Data**
   - Province coordinates (can calculate Manila distance)
   - Region mapping

3. **Contractor Data** (`sec.contractors`)
   - 10,981 unique contractors
   - Project counts
   - SEC verification status
   - Source tracking (Flood, DIME, PhilGEPS)

### ❌ **Critical Missing Data for Full CRI:**

1. **PhilGEPS Extended Contract Data:**
   - Publication date
   - Closing date
   - Contract end date
   - Initial estimated price
   - Entry date into PhilGEPS
   - Number of bidders
   - Winning bid vs other bids

2. **Political Officials Dataset:**
   - Elected officials by province and term
   - Surnames
   - Positions (Governor, Vice-Governor, Board Members, Mayors, Vice-Mayors, Congressmen)
   - Terms: 2004-2007, 2007-2010, 2010-2013, 2013-2016, 2016-2019

3. **Socioeconomic Data:**
   - IRA allocation per province (DOF)
   - Poverty incidence per province (PSA)
   - Population per province (PSA)
   - Ethnolinguistic composition (PSA 2010 census)

---

## Partial Implementation Options

### Option 1: Simplified CRI (3 factors)
Use only the data we have:
- Procurement Mode (business_category)
- Approved Budget (contract_amount)
- Classification (business_category)

**Limitation:** Only 3 of 9 factors = incomplete risk assessment

### Option 2: Contract Quality Score (Our Own)
Create a simpler indicator based on available data:
- Contract amount outliers (statistical deviation)
- Contractor concentration (one contractor getting too many awards)
- Award status anomalies
- Time patterns (rush of awards at fiscal year end)

### Option 3: Full CRI (Requires Data Collection)
1. Scrape detailed PhilGEPS data (timeline, initial estimates, etc.)
2. Obtain political officials dataset (COMELEC, Ateneo dataset?)
3. Get socioeconomic data (PSA, DOF)
4. Implement IRT model
5. Calculate CRI per contract → aggregate to province level

---

## Key Findings from Paper

1. **CRI decreased 2004-2013**, then **increased to all-time high in 2016**

2. **Political HHI → CRI correlation:**
   - Coefficient: 0.002** (significant at 5% level)
   - Example: 200-point HHI increase = 0.4 SD increase in CRI
   - Dinagat Islands (highest HHI 210.48) vs Mountain Province (lowest 3.24)

3. **Largest Dynasty → CRI correlation:**
   - Coefficient: 0.018-0.020*** (significant at 1% level)
   - Strong positive link

4. **Top 15 High-Risk Provinces (2004-2018 average CRI > 0):**
   - Biliran, Eastern Samar, Pangasinan, Marinduque, La Union
   - Agusan del Norte, Batangas, Cavite, Albay, NCR
   - Leyte, Davao del Sur, Samar, Camarines Norte, Tarlac

5. **Population → CRI:**
   - Negative correlation (smaller provinces = higher risk)

---

## Next Steps

### To Implement Full CRI:

1. **Enhance PhilGEPS data collection:**
   - Scrape full contract details from PhilGEPS website
   - Need: Publication dates, closing dates, estimated prices, bidding timeline

2. **Obtain political dynasty data:**
   - Request from Ateneo School of Government
   - OR scrape from COMELEC election results (2004-2019)
   - Build surname-position-province-term database

3. **Collect socioeconomic indicators:**
   - PSA: Poverty, population, ethnicity data
   - DOF: IRA allocations per province

4. **Implement IRT model:**
   - Use Python libraries (`pyirt`, `statsmodels`)
   - Calculate factor loadings
   - Generate CRI scores per contract

5. **Aggregate and analyze:**
   - CRI per province per term
   - Correlation with political dynasties
   - Visualizations and dashboards

---

## Potential Collaboration

**Ateneo Policy Center** (co-authors of the paper) might have:
- The complete PhilGEPS dataset with all 9 factors
- Political officials database
- Processed CRI scores

Contact: Jurel K. Yap (jkyap@ateneo.edu)

---

## Current Capabilities

With our existing data, we can create **partial corruption risk indicators**:

### 1. **Contractor Concentration Risk**
- Measure: HHI for contractors (similar to Political HHI)
- Formula: Sum of (contractor market share)²
- Data: ✅ We have project counts per contractor per province

### 2. **Contract Amount Anomaly Detection**
- Measure: Statistical outliers in contract amounts
- Methods: Z-score, IQR, percentile analysis
- Data: ✅ We have contract amounts by province

### 3. **Procurement Method Distribution**
- Measure: % of contracts by competitive vs non-competitive methods
- Data: ✅ We have `business_category`

### 4. **SEC Verification Rate**
- Measure: % of contractors with valid SEC registration
- Unique to our dataset!
- Data: ✅ We have `sec.contractors` with registration status

These partial indicators could be valuable even without the full CRI calculation.

