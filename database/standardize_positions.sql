
# Position Standardization Script
# This script standardizes position names in the political_dynasties table

UPDATE political_dynasties 
SET position = 'CHIEF JUSTICE' 
WHERE position ILIKE '%CHIEF JUSTICE%' OR position ILIKE '%SUPREME COURT CHIEF%';

UPDATE political_dynasties 
SET position = 'ASSOCIATE JUSTICE' 
WHERE position ILIKE '%ASSOCIATE JUSTICE%' OR position ILIKE '%SUPREME COURT JUSTICE%';

UPDATE political_dynasties 
SET position = 'SECRETARY OF EDUCATION' 
WHERE position ILIKE '%SECRETARY%EDUCATION%' OR position ILIKE '%DEPED SECRETARY%';

UPDATE political_dynasties 
SET position = 'SECRETARY OF HEALTH' 
WHERE position ILIKE '%SECRETARY%HEALTH%' OR position ILIKE '%DOH SECRETARY%';

UPDATE political_dynasties 
SET position = 'SECRETARY OF FINANCE' 
WHERE position ILIKE '%SECRETARY%FINANCE%' OR position ILIKE '%DOF SECRETARY%';

UPDATE political_dynasties 
SET position = 'SECRETARY OF INTERIOR AND LOCAL GOVERNMENT' 
WHERE position ILIKE '%SECRETARY%INTERIOR%' OR position ILIKE '%DILG SECRETARY%';

UPDATE political_dynasties 
SET position = 'CHAIRMAN, COMMISSION ON ELECTIONS' 
WHERE position ILIKE '%COMELEC%CHAIRMAN%' OR position ILIKE '%ELECTIONS%CHAIRMAN%';

UPDATE political_dynasties 
SET position = 'COMMISSIONER, COMMISSION ON ELECTIONS' 
WHERE position ILIKE '%COMELEC%COMMISSIONER%' OR position ILIKE '%ELECTIONS%COMMISSIONER%';

-- Standardize existing positions
UPDATE political_dynasties 
SET position = 'SENATOR' 
WHERE position ILIKE '%SENATOR%';

UPDATE political_dynasties 
SET position = 'MEMBER, HOUSE OF REPRESENTATIVES' 
WHERE position ILIKE '%REPRESENTATIVE%' OR position ILIKE '%CONGRESS%';

UPDATE political_dynasties 
SET position = 'GOVERNOR' 
WHERE position ILIKE '%GOVERNOR%' AND position NOT ILIKE '%VICE%';

UPDATE political_dynasties 
SET position = 'VICE GOVERNOR' 
WHERE position ILIKE '%VICE GOVERNOR%';

UPDATE political_dynasties 
SET position = 'MAYOR' 
WHERE position ILIKE '%MAYOR%' AND position NOT ILIKE '%VICE%';

UPDATE political_dynasties 
SET position = 'VICE MAYOR' 
WHERE position ILIKE '%VICE MAYOR%';

UPDATE political_dynasties 
SET position = 'COUNCILOR' 
WHERE position ILIKE '%COUNCILOR%';
