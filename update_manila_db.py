import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

async def update_district_entries():
    load_dotenv()
    conn = await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        user=os.getenv("POSTGRES_USER", "budget_admin"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        database=os.getenv("POSTGRES_DB_DYNASTY", "dynasty"),
    )
    await conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")

    # MANILA UPDATE
    manila_result = await conn.fetchrow('SELECT data FROM district_entries WHERE name = $1', 'Manila')
    if manila_result:
        manila_data = manila_result['data']
        if isinstance(manila_data, str):
            manila_data = json.loads(manila_data)
    else:
        manila_data = {}

    manila_data.setdefault("entity_type", "city")
    manila_data["barangays"] = {
        "1st District": [f"Barangay {i}" for i in range(1, 147)],
        "2nd District": [f"Barangay {i}" for i in range(147, 267)],
        "3rd District": [f"Barangay {i}" for i in range(268, 395)],
        "4th District": [f"Barangay {i}" for i in range(395, 649)],
        "5th District": [f"Barangay {i}" for i in range(649, 901)],
        "6th District": [f"Barangay {i}" for i in range(901, 1001)],
    }
    manila_data["all_districts"] = [
        "1st District",
        "2nd District",
        "3rd District",
        "4th District",
        "5th District",
        "6th District",
    ]
    manila_data["keywords"] = {
        "1st District": ["Tondo I", "Tondo 1", "Tondo"],
        "2nd District": ["Tondo II", "Tondo 2", "Tondo"],
        "3rd District": ["Quiapo", "Binondo", "San Nicolas", "Sta. Cruz", "Santa Cruz"],
        "4th District": ["Sampaloc"],
        "5th District": ["Paco", "Pandacan", "San Andres", "Sta. Ana", "Santa Ana"],
        "6th District": ["Ermita", "Malate", "Intramuros", "San Miguel", "Port Area"],
    }

    await conn.execute(
        "UPDATE district_entries SET data = $1 WHERE name = $2",
        json.dumps(manila_data),
        "Manila",
    )

    print("✅ Updated Manila district boundaries/keywords in database")

    # LEYTE UPDATE (2nd District keywords)
    leyte_result = await conn.fetchrow('SELECT data FROM district_entries WHERE name = $1', 'Leyte')
    if leyte_result:
        leyte_data = leyte_result['data']
        if isinstance(leyte_data, str):
            leyte_data = json.loads(leyte_data)
    else:
        leyte_data = {}

    keywords = leyte_data.setdefault("keywords", {})
    keywords["2nd District"] = {
        "positive": [
            "Leyte 2nd",
            "2nd LD",
            "Second LD",
            "2nd Legislative District",
            "Second Legislative District",
            "2nd District Engineering",
            "Leyte 2nd DEO",
            "Leyte II",
            "2nd DEO",
            "2nd Legislative Dist.",
            "Leyte 2 DEO",
        ],
        "negative": [
            "Leyte 1st",
            "Leyte 3rd",
            "Leyte 4th",
            "Leyte 5th",
            "Leyte 6th",
            "1st LD",
            "3rd LD",
            "4th LD",
            "5th LD",
            "6th LD",
            "Southern Leyte",
            "Northern Samar",
            "Eastern Samar",
            "Western Samar",
            "Samar Province",
            "Biliran",
            "Ormoc",
            "Tacloban",
            "Leyte I DEO",
            "Leyte 1 DEO",
            "Leyte 3 DEO",
            "Leyte 4 DEO",
            "Leyte 5 DEO",
            "Leyte 6 DEO",
        ],
    }

    await conn.execute(
        "UPDATE district_entries SET data = $1 WHERE name = $2",
        json.dumps(leyte_data),
        "Leyte",
    )

    print("✅ Updated Leyte keywords in database")


    # SAMAR UPDATE (1st District keywords)
    samar_result = await conn.fetchrow('SELECT data FROM district_entries WHERE name = $1', 'Samar')
    if samar_result:
        samar_data = samar_result['data']
        if isinstance(samar_data, str):
            samar_data = json.loads(samar_data)
    else:
        samar_data = {}

    samar_keywords = samar_data.setdefault('keywords', {})
    samar_keywords['1st District'] = {
        'positive': [
            'Samar 1st',
            '1st LD',
            'First LD',
            '1st Legislative District',
            'First Legislative District',
            'Samar 1st DEO',
            'Samar I',
            'Samar 1st Engineering',
            '1st DEO',
            'Samar 1 DEO',
            'Calbayog City DEO',
            'Calbayog 1st'
        ],
        'negative': [
            'Samar 2nd',
            'Samar 3rd',
            '2nd LD',
            'Second LD',
            '3rd LD',
            'Third LD',
            'Eastern Samar',
            'Northern Samar',
            'Western Samar',
            'Catbalogan',
            'Southern Leyte'
        ]
    }

    await conn.execute(
        "UPDATE district_entries SET data = $1 WHERE name = $2",
        json.dumps(samar_data),
        'Samar'
    )

    print('✅ Updated Samar keywords in database')

    await conn.close()

asyncio.run(update_district_entries())
