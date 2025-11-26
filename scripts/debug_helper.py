
    def debug_mikee_romero(self, congressmen_data):
        for name, data in congressmen_data.items():
            if "Romero" in name:
                print(f"DEBUG: {name}")
                print(f"  Provinces: {data.get('provinces')}")
                print(f"  Contractors: {data.get('contractors')}")
                print(f"  Patterns: {data.get('contractor_patterns')}")







