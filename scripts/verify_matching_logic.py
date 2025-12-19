
import unittest

def normalize_for_match(text):
    import unicodedata
    import re
    if not text: return ""
    try:
        text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII')
        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)
        text = text.strip()
        text = text.replace("city of ", "").replace("municipality of ", "")
    except:
        return ""
    return text

class TestMatchingLogic(unittest.TestCase):
    def test_stopwords_exclusion(self):
        # The corrected STOPWORDS list (without "multi-purpose", "building")
        STOPWORDS = {
            "construction", "completion", "rehabilitation", "improvement", "repair", "maintenance", 
            "upgrading", "widening", "concreting", "asphalt", "overlay", "reblocking", 
            "school", "classroom", "infra", "infrastructure",
            "project", "program", "phase", "package", "contract", "id", "no", "of", "the", "in", 
            "and", "to", "with", "at", "city", "province", "municipality", "barangay", "district",
            "st.", "ave.", "rd.", "ext.", "brgy", "poblacion", "water", "system", "flood", "control"
        }
        
        project_name = "CONSTRUCTION OF MULTI-PURPOSE BUILDING"
        norm = normalize_for_match(project_name)
        # Expected norm: "construction of multi purpose building"
        
        tokens = set([t for t in norm.split() if len(t) > 2 and t not in STOPWORDS])
        
        print(f"Project: {project_name}")
        print(f"Tokens: {tokens}")
        
        self.assertIn("multi", tokens)
        self.assertIn("purpose", tokens)
        self.assertIn("building", tokens)
        self.assertNotIn("construction", tokens) # Should be stopped
        
    def test_complex_mpb_name(self):
         # The corrected STOPWORDS list
        STOPWORDS = {
            "construction", "completion", "rehabilitation", "improvement", "repair", "maintenance", 
            "upgrading", "widening", "concreting", "asphalt", "overlay", "reblocking", 
            "school", "classroom", "infra", "infrastructure",
            "project", "program", "phase", "package", "contract", "id", "no", "of", "the", "in", 
            "and", "to", "with", "at", "city", "province", "municipality", "barangay", "district",
            "st.", "ave.", "rd.", "ext.", "brgy", "poblacion", "water", "system", "flood", "control"
        }

        project_name = "CONSTRUCTION OF 2STY2CL, BUENAVISTA ELEMENTARY SCHOOL, MULTI-PURPOSE BUILDING"
        norm = normalize_for_match(project_name)
        tokens = set([t for t in norm.split() if len(t) > 2 and t not in STOPWORDS])
        
        print(f"Project: {project_name}")
        print(f"Tokens: {tokens}")
        
        self.assertIn("multi", tokens)
        self.assertIn("purpose", tokens)
        self.assertIn("building", tokens)

if __name__ == '__main__':
    unittest.main()
