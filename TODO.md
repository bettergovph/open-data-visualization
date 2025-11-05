# TODO

## Deputy Speakers Project Analysis

### Add More Names to List

The `/dynasty-projects` page currently tracks 6 congressmen (Deputy Speakers). We need to add more names from the Deputy Speakers database.

**Current List (6 names):**
1. Martin Romualdez
2. Zaldy Co (Elizaldy Salcedo Co)
3. David Suarez
4. Aurelio Gonzales Jr.
5. Mannix Dalipe (Manuel Jose Dalipe)
6. Edwin Gardiola (Tirso Edwin Loleng Gardiola)

**Reference: Deputy Speakers Database**
- Source: `database/Philippine_Deputy_Speakers_2016-2025.csv`
- Contains 67 unique Deputy Speaker names from 17th-20th Congress (2016-2025)

**All Deputy Speakers from Database (67 names):**
1. Abraham Tolentino
2. Arnie Teves
3. Arthur C. Yap
4. Aurelio Gonzales Jr. ✓ (already tracked)
5. Bai Sandra Sema
6. Benny Abante
7. Bernadette Herrera
8. Bojie Dy
9. Camille Villar
10. Conrado Estrella III
11. Dan Fernandez
12. David Suarez ✓ (already tracked)
13. Deogracias Victor Savellano
14. Divina Grace Yu
15. Duke Frasco
16. Eddie Villanueva
17. Eric Martinez
18. Eric Singson
19. Evelina Escudero
20. Ferdinand Hernandez
21. Ferjenel Biron
22. Fredenil Castro
23. Frederick Abueg
24. Gloria Macapagal Arroyo
25. Gwendolyn Garcia
26. Henry Oaminal
27. Isidro Ungab
28. Janette Garin
29. Jay Khonghun
30. Johnny Pimentel
31. Juan Pablo Bondoc
32. Kristine Singson-Meehan
33. Len Alonte
34. Linabelle Villarica
35. Lito Atienza
36. Loren Legarda
37. Luis Raymund Villafuerte
38. Mercedes Alvarez
39. Mikee Romero
40. Miro Quimbo
41. Mujiv Hataman
42. Mylene Garcia-Albano
43. Neptali Gonzales II
44. Pablo John Garcia
45. Paolo Duterte
46. Paolo Ortega
47. Paulino Salvador Leachon
48. Pia Cayetano
49. Prospero Pichay Jr.
50. Ralph Recto
51. Randolph Ting
52. Raneo Abu
53. Raymond Mendoza
54. Roberto Puno
55. Rodante Marcoleta
56. Rogelio Pacquiao
57. Rolando Andaya Jr.
58. Ronaldo Puno
59. Rose Marie Arenas
60. Rufus Rodriguez
61. Sharon Garin
62. Strike Revilla
63. Tonypet Albano
64. Vilma Santos
65. Wes Gatchalian
66. Yasser Balindong
67. Yevgeny Emano

**Action Required:**
- Add remaining Deputy Speaker names to `dynasty-projects-config.json`
- Use `database/Philippine_Deputy_Speakers_2016-2025.csv` as reference for names and districts
- Update district information for each new name
- Add contractor associations where applicable
- Regenerate cache using `scripts/generate_dynasty_projects_cache.py`

**Files to Update:**
- `dynasty-projects-config.json` - Add new congressmen entries
- `districts.json` - Add district mappings if needed
- `scripts/generate_dynasty_projects_cache.py` - Verify it handles all names correctly

**Notes:**
- Ensure all names match exactly with the `political_dynasties` table in the database
- Verify district coverage for each new congressman (check CSV for district information)
- Add contractor patterns if they have known contractor relationships
- Some names may need normalization (e.g., "Zaldy Co" = "Elizaldy Salcedo Co", "Mannix Dalipe" = "Manuel Jose Dalipe")

