"""PH location DB shared text rules. Generated ODV copy; edit in NEP location_data.

Metadata stripping affects address lookup only, never source titles or scope.
Confirmed name spellings retain geographic levels, parents and source identities.
"""
import re
import unicodedata

def text_key(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(c for c in value if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", value).strip()


def confirmed_name_key(value):
    # User-confirmed complete-name spellings only. Never replace a token inside
    # a longer name, and never merge distinct geographic levels or parents.
    if value in {"santo nino", "sto. nino", "sto nino", "sto. ni±o", "sto ni±o"}:
        return "santo nino"
    return value


def place_key(value):
    # City labels are structural aliases; directions and other name words stay.
    value = text_key(value)
    value = re.sub(r"\s*\(capital\)\s*", "", value)
    value = re.sub(r"^(?:city of|municipality of|province of)\s+", "", value)
    value = re.sub(r"\s+city$", "", value)
    return confirmed_name_key(re.sub(r"\s+", " ", value).strip(" ."))


def geographic_title(value):
    """Remove trailing station/coordinate metadata, never route/place wording."""
    text = text_key(value)
    removed=[]
    marker=r"(?:sta(?:tion)?|chainage|km|kilomet(?:er|re)|k)\.?\s*[:=]?\s*"
    number=r"[+-]?\d+(?:\.\d+)?"
    offset=r"(?:"+number+r"|\(\s*"+number+r"\s*\))"
    point=r"\+?\s*\d+(?:\.\d+)?\s*(?:\+\s*"+offset+r")?"
    station=re.compile(marker+point+r"(?:\s*(?:[-–—]|to)\s*(?:"+marker+r")?"+point+r")?(?:\s+(?:ls|rs|bs))?",re.I)
    coordinate=re.compile(r"(\d{1,2}\.\d+)\s*°?\s*,\s*(\d{2,3}\.\d+)\s*°?")

    def coordinates(annotation):
        pair=coordinate.fullmatch(annotation.strip())
        return bool(pair and 4<=float(pair[1])<=22 and 116<=float(pair[2])<=127)

    # Inspect a balanced final parenthesis group before splitting comma fields.
    # Nested parentheses are allowed only inside complete numeric offsets.
    # Route endpoints, place names and mixed comments never satisfy the grammar.
    while text.endswith(')'):
        depth=0;start=None
        for i in range(len(text)-1,-1,-1):
            if text[i]==')':depth+=1
            elif text[i]=='(':
                depth-=1
                if depth==0:start=i;break
        if start is None or (start and not (text[start-1].isspace() or text[start-1]==',')):
            break
        annotation=text[start+1:-1].strip()
        chunks=[c.strip() for c in re.split(r'[,;]',annotation)]
        if not (coordinates(annotation) or (chunks and all(station.fullmatch(c) for c in chunks))):
            break
        removed.insert(0,text[start:]);text=text[:start].rstrip(' ,')
    fields = [f.strip() for f in text.split(",")]
    if len(fields)>=3 and coordinates(','.join(fields[-2:])):
        removed[0:0]=fields[-2:];fields=fields[:-2]
    while fields and station.fullmatch(fields[-1]):removed.insert(0,fields.pop())
    if fields:
        # A metadata marker may immediately follow a province field. The
        # remaining field must still match an exact jurisdiction in resolve().
        match=re.search(r"\s+(?="+marker+r")",fields[-1])
        if match and station.fullmatch(fields[-1][match.end():]):
            removed.insert(0,fields[-1][match.end():]);fields[-1]=fields[-1][:match.start()].strip()
    return ",".join(fields),removed


def barangay_key(value):
    return confirmed_name_key(re.sub(r"^(?:barangay|brgy\.?|bgy\.?)\s+", "", text_key(value)).strip(" ."))
