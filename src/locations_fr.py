# -*- coding: utf-8 -*-
"""
FRANCE LOCATIONS & COORDINATES FOR GOOGLE MAPS SCRAPING
======================================================
Covers all 13 Metropolitan Regions of France:
- Paris 20 Arrondissements + Île-de-France hubs
- All top French metropolitan areas & urban communities
- Zoom level: 13-14 for high-density nail & beauty salon detection
"""

LOCATIONS = [
    # ---------------------------------------------------------
    # 1. PARIS (20 Arrondissements)
    # ---------------------------------------------------------
    {"region": "Île-de-France", "department": "Paris", "name": "Paris 1er Arrondissement (Louvre / Palais-Royal)", "lat": 48.8606, "lng": 2.3376, "zoom": 14},
    {"region": "Île-de-France", "department": "Paris", "name": "Paris 2e Arrondissement (Bourse / Sentier)", "lat": 48.8682, "lng": 2.3428, "zoom": 14},
    {"region": "Île-de-France", "department": "Paris", "name": "Paris 3e Arrondissement (Temple / Marais)", "lat": 48.8637, "lng": 2.3615, "zoom": 14},
    {"region": "Île-de-France", "department": "Paris", "name": "Paris 4e Arrondissement (Hôtel-de-Ville / Marais)", "lat": 48.8543, "lng": 2.3576, "zoom": 14},
    {"region": "Île-de-France", "department": "Paris", "name": "Paris 5e Arrondissement (Panthéon / Quartier Latin)", "lat": 48.8449, "lng": 2.3498, "zoom": 14},
    {"region": "Île-de-France", "department": "Paris", "name": "Paris 6e Arrondissement (Luxembourg / Saint-Germain)", "lat": 48.8499, "lng": 2.3328, "zoom": 14},
    {"region": "Île-de-France", "department": "Paris", "name": "Paris 7e Arrondissement (Palais-Bourbon / Tour Eiffel)", "lat": 48.8561, "lng": 2.3126, "zoom": 14},
    {"region": "Île-de-France", "department": "Paris", "name": "Paris 8e Arrondissement (Champs-Élysées / Madeleine)", "lat": 48.8727, "lng": 2.3126, "zoom": 14},
    {"region": "Île-de-France", "department": "Paris", "name": "Paris 9e Arrondissement (Opéra / Haussmann)", "lat": 48.8760, "lng": 2.3374, "zoom": 14},
    {"region": "Île-de-France", "department": "Paris", "name": "Paris 10e Arrondissement (Gare du Nord / Canal Saint-Martin)", "lat": 48.8761, "lng": 2.3601, "zoom": 14},
    {"region": "Île-de-France", "department": "Paris", "name": "Paris 11e Arrondissement (Bastille / République / Voltaire)", "lat": 48.8594, "lng": 2.3786, "zoom": 14},
    {"region": "Île-de-France", "department": "Paris", "name": "Paris 12e Arrondissement (Gare de Lyon / Bercy / Nation)", "lat": 48.8397, "lng": 2.3877, "zoom": 14},
    {"region": "Île-de-France", "department": "Paris", "name": "Paris 13e Arrondissement (Place d'Italie / Olympiades)", "lat": 48.8284, "lng": 2.3623, "zoom": 14},
    {"region": "Île-de-France", "department": "Paris", "name": "Paris 14e Arrondissement (Montparnasse / Alésia)", "lat": 48.8299, "lng": 2.3271, "zoom": 14},
    {"region": "Île-de-France", "department": "Paris", "name": "Paris 15e Arrondissement (Vaugirard / Convention / Grenelle)", "lat": 48.8413, "lng": 2.2998, "zoom": 14},
    {"region": "Île-de-France", "department": "Paris", "name": "Paris 16e Arrondissement (Trocadéro / Passy / Auteuil)", "lat": 48.8604, "lng": 2.2708, "zoom": 14},
    {"region": "Île-de-France", "department": "Paris", "name": "Paris 17e Arrondissement (Batignolles / Ternes / Épinettes)", "lat": 48.8835, "lng": 2.3080, "zoom": 14},
    {"region": "Île-de-France", "department": "Paris", "name": "Paris 18e Arrondissement (Montmartre / Clignancourt)", "lat": 48.8913, "lng": 2.3444, "zoom": 14},
    {"region": "Île-de-France", "department": "Paris", "name": "Paris 19e Arrondissement (Villette / Buttes-Chaumont)", "lat": 48.8827, "lng": 2.3822, "zoom": 14},
    {"region": "Île-de-France", "department": "Paris", "name": "Paris 20e Arrondissement (Belleville / Ménilmontant / Gambetta)", "lat": 48.8632, "lng": 2.3985, "zoom": 14},

    # ---------------------------------------------------------
    # 2. ÎLE-DE-FRANCE (Petite & Grande Couronne)
    # ---------------------------------------------------------
    {"region": "Île-de-France", "department": "Hauts-de-Seine", "name": "Boulogne-Billancourt", "lat": 48.8353, "lng": 2.2412, "zoom": 13},
    {"region": "Île-de-France", "department": "Hauts-de-Seine", "name": "Nanterre / La Défense", "lat": 48.8924, "lng": 2.2071, "zoom": 13},
    {"region": "Île-de-France", "department": "Hauts-de-Seine", "name": "Courbevoie / Puteaux", "lat": 48.8974, "lng": 2.2562, "zoom": 13},
    {"region": "Île-de-France", "department": "Hauts-de-Seine", "name": "Asnières-sur-Seine / Colombes", "lat": 48.9107, "lng": 2.2889, "zoom": 13},
    {"region": "Île-de-France", "department": "Hauts-de-Seine", "name": "Rueil-Malmaison", "lat": 48.8778, "lng": 2.1804, "zoom": 13},
    {"region": "Île-de-France", "department": "Hauts-de-Seine", "name": "Issy-les-Moulineaux / Clamart", "lat": 48.8241, "lng": 2.2736, "zoom": 13},
    {"region": "Île-de-France", "department": "Seine-Saint-Denis", "name": "Saint-Denis", "lat": 48.9362, "lng": 2.3574, "zoom": 13},
    {"region": "Île-de-France", "department": "Seine-Saint-Denis", "name": "Montreuil", "lat": 48.8638, "lng": 2.4485, "zoom": 13},
    {"region": "Île-de-France", "department": "Seine-Saint-Denis", "name": "Aulnay-sous-Bois", "lat": 48.9386, "lng": 2.4939, "zoom": 13},
    {"region": "Île-de-France", "department": "Seine-Saint-Denis", "name": "Aubervilliers / Pantin", "lat": 48.9135, "lng": 2.3831, "zoom": 13},
    {"region": "Île-de-France", "department": "Val-de-Marne", "name": "Créteil", "lat": 48.7904, "lng": 2.4556, "zoom": 13},
    {"region": "Île-de-France", "department": "Val-de-Marne", "name": "Vitry-sur-Seine / Ivry-sur-Seine", "lat": 48.7876, "lng": 2.3926, "zoom": 13},
    {"region": "Île-de-France", "department": "Val-de-Marne", "name": "Champigny-sur-Marne / Saint-Maur", "lat": 48.8172, "lng": 2.5156, "zoom": 13},
    {"region": "Île-de-France", "department": "Yvelines", "name": "Versailles", "lat": 48.8049, "lng": 2.1204, "zoom": 13},
    {"region": "Île-de-France", "department": "Yvelines", "name": "Saint-Germain-en-Laye", "lat": 48.8989, "lng": 2.0938, "zoom": 13},
    {"region": "Île-de-France", "department": "Val-d'Oise", "name": "Argenteuil", "lat": 48.9479, "lng": 2.2478, "zoom": 13},
    {"region": "Île-de-France", "department": "Val-d'Oise", "name": "Cergy / Pontoise", "lat": 49.0361, "lng": 2.0772, "zoom": 13},
    {"region": "Île-de-France", "department": "Essonne", "name": "Évry-Courcouronnes", "lat": 48.6238, "lng": 2.4296, "zoom": 13},

    # ---------------------------------------------------------
    # 3. AUVERGNE-RHÔNE-ALPES (Lyon & Métropoles)
    # ---------------------------------------------------------
    {"region": "Auvergne-Rhône-Alpes", "department": "Rhône", "name": "Lyon Presqu'île (1er & 2e Arr.)", "lat": 45.7597, "lng": 4.8322, "zoom": 14},
    {"region": "Auvergne-Rhône-Alpes", "department": "Rhône", "name": "Lyon Part-Dieu / Préfecture (3e Arr.)", "lat": 45.7601, "lng": 4.8588, "zoom": 14},
    {"region": "Auvergne-Rhône-Alpes", "department": "Rhône", "name": "Lyon Croix-Rousse / Caluire (4e Arr.)", "lat": 45.7772, "lng": 4.8286, "zoom": 14},
    {"region": "Auvergne-Rhône-Alpes", "department": "Rhône", "name": "Lyon Brotteaux / Masséna (6e Arr.)", "lat": 45.7698, "lng": 4.8569, "zoom": 14},
    {"region": "Auvergne-Rhône-Alpes", "department": "Rhône", "name": "Lyon Guillotière / Gerland (7e Arr.)", "lat": 45.7368, "lng": 4.8375, "zoom": 14},
    {"region": "Auvergne-Rhône-Alpes", "department": "Rhône", "name": "Villeurbanne (Gratte-Ciel / Charpennes)", "lat": 45.7667, "lng": 4.8833, "zoom": 14},
    {"region": "Auvergne-Rhône-Alpes", "department": "Isère", "name": "Grenoble", "lat": 45.1885, "lng": 5.7245, "zoom": 13},
    {"region": "Auvergne-Rhône-Alpes", "department": "Loire", "name": "Saint-Étienne", "lat": 45.4397, "lng": 4.3872, "zoom": 13},
    {"region": "Auvergne-Rhône-Alpes", "department": "Puy-de-Dôme", "name": "Clermont-Ferrand", "lat": 45.7772, "lng": 3.0870, "zoom": 13},
    {"region": "Auvergne-Rhône-Alpes", "department": "Haute-Savoie", "name": "Annecy", "lat": 45.8992, "lng": 6.1294, "zoom": 13},
    {"region": "Auvergne-Rhône-Alpes", "department": "Savoie", "name": "Chambéry", "lat": 45.5646, "lng": 5.9178, "zoom": 13},
    {"region": "Auvergne-Rhône-Alpes", "department": "Drôme", "name": "Valence", "lat": 44.9333, "lng": 4.8917, "zoom": 13},

    # ---------------------------------------------------------
    # 4. PROVENCE-ALPES-CÔTE D'AZUR (Marseille, Nice, Côte d'Azur)
    # ---------------------------------------------------------
    {"region": "Provence-Alpes-Côte d'Azur", "department": "Bouches-du-Rhône", "name": "Marseille Vieux-Port / Centre (1er & 6e Arr.)", "lat": 43.2965, "lng": 5.3698, "zoom": 14},
    {"region": "Provence-Alpes-Côte d'Azur", "department": "Bouches-du-Rhône", "name": "Marseille Prado / Castellane (8e Arr.)", "lat": 43.2684, "lng": 5.3855, "zoom": 14},
    {"region": "Provence-Alpes-Côte d'Azur", "department": "Bouches-du-Rhône", "name": "Aix-en-Provence", "lat": 43.5297, "lng": 5.4474, "zoom": 13},
    {"region": "Provence-Alpes-Côte d'Azur", "department": "Alpes-Maritimes", "name": "Nice Centre (Jean Médecin / Masséna)", "lat": 43.7031, "lng": 7.2661, "zoom": 14},
    {"region": "Provence-Alpes-Côte d'Azur", "department": "Alpes-Maritimes", "name": "Nice Vieux-Nice / Port", "lat": 43.6961, "lng": 7.2785, "zoom": 14},
    {"region": "Provence-Alpes-Côte d'Azur", "department": "Alpes-Maritimes", "name": "Cannes", "lat": 43.5528, "lng": 7.0174, "zoom": 13},
    {"region": "Provence-Alpes-Côte d'Azur", "department": "Alpes-Maritimes", "name": "Antibes / Juan-les-Pins", "lat": 43.5808, "lng": 7.1239, "zoom": 13},
    {"region": "Provence-Alpes-Côte d'Azur", "department": "Var", "name": "Toulon", "lat": 43.1242, "lng": 5.9280, "zoom": 13},
    {"region": "Provence-Alpes-Côte d'Azur", "department": "Vaucluse", "name": "Avignon", "lat": 43.9493, "lng": 4.8055, "zoom": 13},

    # ---------------------------------------------------------
    # 5. OCCITANIE (Toulouse, Montpellier)
    # ---------------------------------------------------------
    {"region": "Occitanie", "department": "Haute-Garonne", "name": "Toulouse Centre (Capitole / Jean Jaurès)", "lat": 43.6047, "lng": 1.4442, "zoom": 14},
    {"region": "Occitanie", "department": "Haute-Garonne", "name": "Toulouse Saint-Cyprien / Carmes", "lat": 43.5976, "lng": 1.4382, "zoom": 14},
    {"region": "Occitanie", "department": "Hérault", "name": "Montpellier Centre (Place de la Comédie / Écusson)", "lat": 43.6085, "lng": 3.8795, "zoom": 14},
    {"region": "Occitanie", "department": "Hérault", "name": "Montpellier Antigone / Port Marianne", "lat": 43.6026, "lng": 3.8967, "zoom": 14},
    {"region": "Occitanie", "department": "Gard", "name": "Nîmes", "lat": 43.8367, "lng": 4.3601, "zoom": 13},
    {"region": "Occitanie", "department": "Pyrénées-Orientales", "name": "Perpignan", "lat": 42.6887, "lng": 2.8948, "zoom": 13},
    {"region": "Occitanie", "department": "Hérault", "name": "Béziers", "lat": 43.3444, "lng": 3.2158, "zoom": 13},

    # ---------------------------------------------------------
    # 6. NOUVELLE-AQUITAINE (Bordeaux & Sud-Ouest)
    # ---------------------------------------------------------
    {"region": "Nouvelle-Aquitaine", "department": "Gironde", "name": "Bordeaux Centre (Triangle d'Or / Sainte-Catherine)", "lat": 44.8378, "lng": -0.5792, "zoom": 14},
    {"region": "Nouvelle-Aquitaine", "department": "Gironde", "name": "Bordeaux Chartrons / Bassins à Flot", "lat": 44.8546, "lng": -0.5714, "zoom": 14},
    {"region": "Nouvelle-Aquitaine", "department": "Gironde", "name": "Mérignac / Pessac", "lat": 44.8386, "lng": -0.6436, "zoom": 13},
    {"region": "Nouvelle-Aquitaine", "department": "Pyrénées-Atlantiques", "name": "Pau", "lat": 43.2951, "lng": -0.3708, "zoom": 13},
    {"region": "Nouvelle-Aquitaine", "department": "Pyrénées-Atlantiques", "name": "Bayonne / Biarritz / Anglet", "lat": 43.4929, "lng": -1.4748, "zoom": 13},
    {"region": "Nouvelle-Aquitaine", "department": "Charente-Maritime", "name": "La Rochelle", "lat": 46.1603, "lng": -1.1511, "zoom": 13},
    {"region": "Nouvelle-Aquitaine", "department": "Haute-Vienne", "name": "Limoges", "lat": 45.8336, "lng": 1.2611, "zoom": 13},
    {"region": "Nouvelle-Aquitaine", "department": "Vienne", "name": "Poitiers", "lat": 46.5802, "lng": 0.3404, "zoom": 13},

    # ---------------------------------------------------------
    # 7. HAUTS-DE-FRANCE (Lille & Nord)
    # ---------------------------------------------------------
    {"region": "Hauts-de-France", "department": "Nord", "name": "Lille Centre & Vieux-Lille", "lat": 50.6292, "lng": 3.0573, "zoom": 14},
    {"region": "Hauts-de-France", "department": "Nord", "name": "Roubaix / Tourcoing", "lat": 50.6927, "lng": 3.1778, "zoom": 13},
    {"region": "Hauts-de-France", "department": "Somme", "name": "Amiens", "lat": 49.8941, "lng": 2.2958, "zoom": 13},
    {"region": "Hauts-de-France", "department": "Nord", "name": "Dunkerque", "lat": 51.0343, "lng": 2.3768, "zoom": 13},
    {"region": "Hauts-de-France", "department": "Pas-de-Calais", "name": "Calais", "lat": 50.9513, "lng": 1.8587, "zoom": 13},

    # ---------------------------------------------------------
    # 8. GRAND EST (Strasbourg, Reims, Nancy, Metz)
    # ---------------------------------------------------------
    {"region": "Grand Est", "department": "Bas-Rhin", "name": "Strasbourg Centre (Grande-Île / Petite France)", "lat": 48.5734, "lng": 7.7521, "zoom": 14},
    {"region": "Grand Est", "department": "Bas-Rhin", "name": "Strasbourg Neudorf / Esplanade", "lat": 48.5684, "lng": 7.7645, "zoom": 14},
    {"region": "Grand Est", "department": "Marne", "name": "Reims Centre", "lat": 49.2583, "lng": 4.0317, "zoom": 13},
    {"region": "Grand Est", "department": "Moselle", "name": "Metz", "lat": 49.1193, "lng": 6.1757, "zoom": 13},
    {"region": "Grand Est", "department": "Meurthe-et-Moselle", "name": "Nancy", "lat": 48.6921, "lng": 6.1844, "zoom": 13},
    {"region": "Grand Est", "department": "Haut-Rhin", "name": "Mulhouse", "lat": 47.7508, "lng": 7.3359, "zoom": 13},
    {"region": "Grand Est", "department": "Haut-Rhin", "name": "Colmar", "lat": 48.0794, "lng": 7.3582, "zoom": 13},

    # ---------------------------------------------------------
    # 9. PAYS DE LA LOIRE (Nantes, Angers, Le Mans)
    # ---------------------------------------------------------
    {"region": "Pays de la Loire", "department": "Loire-Atlantique", "name": "Nantes Centre (Commerce / Graslin)", "lat": 47.2184, "lng": -1.5536, "zoom": 14},
    {"region": "Pays de la Loire", "department": "Loire-Atlantique", "name": "Nantes Île de Nantes / Beaulieu", "lat": 47.2064, "lng": -1.5422, "zoom": 14},
    {"region": "Pays de la Loire", "department": "Maine-et-Loire", "name": "Angers", "lat": 47.4784, "lng": -0.5632, "zoom": 13},
    {"region": "Pays de la Loire", "department": "Sarthe", "name": "Le Mans", "lat": 48.0061, "lng": 0.1996, "zoom": 13},
    {"region": "Pays de la Loire", "department": "Loire-Atlantique", "name": "Saint-Nazaire", "lat": 47.2735, "lng": -2.2137, "zoom": 13},

    # ---------------------------------------------------------
    # 10. BRETAGNE (Rennes, Brest)
    # ---------------------------------------------------------
    {"region": "Bretagne", "department": "Ille-et-Vilaine", "name": "Rennes Centre (Sainte-Anne / République)", "lat": 48.1173, "lng": -1.6778, "zoom": 14},
    {"region": "Bretagne", "department": "Finistère", "name": "Brest", "lat": 48.3904, "lng": -4.4861, "zoom": 13},
    {"region": "Bretagne", "department": "Finistère", "name": "Quimper", "lat": 47.9960, "lng": -4.0999, "zoom": 13},
    {"region": "Bretagne", "department": "Morbihan", "name": "Lorient / Vannes", "lat": 47.7483, "lng": -3.3667, "zoom": 13},
    {"region": "Bretagne", "department": "Ille-et-Vilaine", "name": "Saint-Malo", "lat": 48.6493, "lng": -2.0257, "zoom": 13},

    # ---------------------------------------------------------
    # 11. NORMANDIE (Rouen, Le Havre, Caen)
    # ---------------------------------------------------------
    {"region": "Normandie", "department": "Seine-Maritime", "name": "Rouen", "lat": 49.4432, "lng": 1.0999, "zoom": 13},
    {"region": "Normandie", "department": "Seine-Maritime", "name": "Le Havre", "lat": 49.4944, "lng": 0.1079, "zoom": 13},
    {"region": "Normandie", "department": "Calvados", "name": "Caen", "lat": 49.1829, "lng": -0.3707, "zoom": 13},

    # ---------------------------------------------------------
    # 12. BOURGOGNE-FRANCHE-COMTÉ (Dijon, Besançon)
    # ---------------------------------------------------------
    {"region": "Bourgogne-Franche-Comté", "department": "Côte-d'Or", "name": "Dijon", "lat": 47.3220, "lng": 5.0415, "zoom": 13},
    {"region": "Bourgogne-Franche-Comté", "department": "Doubs", "name": "Besançon", "lat": 47.2378, "lng": 6.0241, "zoom": 13},

    # ---------------------------------------------------------
    # 13. CENTRE-VAL DE LOIRE (Tours, Orléans)
    # ---------------------------------------------------------
    {"region": "Centre-Val de Loire", "department": "Indre-et-Loire", "name": "Tours", "lat": 47.3941, "lng": 0.6848, "zoom": 13},
    {"region": "Centre-Val de Loire", "department": "Loiret", "name": "Orléans", "lat": 47.9030, "lng": 1.9093, "zoom": 13},
]
