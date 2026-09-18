def extraire_rotations_pdf(pdf_file, data_transport, dist_base):
    rotations = []
    EXCLUSIONS = ['CDG', 'ORY', 'PAR', 'MMA', 'LLA', 'XPL', 'RES', 'MCP', 'DEP', 'ARR', 
                  'CIE', 'VOL', 'TVA', 'NET', 'EUR', 'SIT', 'PNC', 'PNT', 
                  'JAN', 'FEV', 'MAR', 'AVR', 'MAI', 'JUI', 'AOU', 'SEP', 'OCT', 'NOV', 'DEC',
                  'SST', 'SLT', 'SLK', 'REC', 'REO', 'VAP', 'ENF', 'AIO', 'FC2', 'XXX',
                  'HCT', 'HCA', 'HCV', 'VLD', 'CAC', 'REP', 'NON', 'AIC', 'SOL', 'TSV', 'IRG', 'SAB', 'CMT', 'MF', 'VRC', 'VR2']

    try:
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                text = page.extract_text(layout=False)
                if not text:
                    page.flush_cache()
                    continue
                text_upper = text.upper()

                if "FEUILLE HORAIRE" not in text_upper:
                    page.flush_cache()
                    continue 

                if "FEUILLE HORAIRE D'ACTIVITE" in text_upper:
                    text_upper = text_upper.split("FEUILLE HORAIRE D'ACTIVITE")[-1]

                if "FEUILLE DE DECOMPTE" in text_upper:
                    text_upper = text_upper.split("FEUILLE DE DECOMPTE")[0]
                if "FRAIS DE DEPLACEMENT" in text_upper:
                    text_upper = text_upper.split("FRAIS DE DEPLACEMENT")[0]

                lignes_utiles = [l for l in text_upper.split('\n') if "CUMUL" not in l.replace(" ", "")]
                text_clean_mois = '\n'.join(lignes_utiles).replace('É', 'E').replace('Û', 'U')
                current_month = "Inconnu"

                for m in reversed(LISTE_MOIS):
                    mois_format = m.upper().replace('É', 'E').replace('Û', 'U')
                    if re.search(rf"\b{mois_format}\s*20\d\d\b", text_clean_mois):
                        current_month = m
                        break

                if current_month == "Inconnu":
                    for m in reversed(LISTE_MOIS):
                        if m.upper().replace('É', 'E').replace('Û', 'U') in text_clean_mois:
                            current_month = m
                            break

                lines = text_clean_mois.split('\n')

                for line in lines:
                    codes_3lettres = re.findall(r'\b([A-Z]{3})\b', line)
                    for code in codes_3lettres:
                        if code in [m.upper() for m in LISTE_MOIS]:
                            continue

                        # Traitement des Activités (Sol, Réserve, etc.)
                        if code in REF_ACTIVITES:
                            dates_vols = re.findall(r'\b(0?[1-9]|[12][0-9]|3[01])\s*(?:\|)?\s*(?:[01][0-9]|2[0-3])[.:][0-9]{2}\b', line)
                            if dates_vols: jour_dep = int(dates_vols[0])
                            else:
                                jours = re.findall(r'\b(0?[1-9]|[12][0-9]|3[01])\b', line)
                                jour_dep = int(jours[0]) if jours else 1

                            # Doublon strict : Même mois + Même jour + Même code d'activité
                            doublon = any(
                                r['mois'] == current_month and r['jour_dep'] == jour_dep and r['arrivee'] == code 
                                for r in rotations
                            )

                            if not doublon:
                                info = REF_ACTIVITES[code]
                                km = dist_base * 2 if (data_transport == 'Voiture' and info['genere_km'] == 'OUI') else 0
                                rotations.append({
                                    'mois': current_month, 'mode': info['categorie'],
                                    'jour_dep': jour_dep, 'jour_arr': jour_dep,
                                    'arrivee': code, 'details': f"{code} ({info['libelle']})",
                                    'nb_jours': 1, 'total': 0.0, 'km': km,
                                    'ville': 'Base', 'pays': 'France', 'taux': 0.0
                                })

                        # Traitement des Escale / Vol (Codes IATA)
                        elif code in REF_IATA and code not in EXCLUSIONS:
                            dates_vols = re.findall(r'\b(0?[1-9]|[12][0-9]|3[01])\s*(?:\|)?\s*(?:[01][0-9]|2[0-3])[.:][0-9]{2}\b', line)
                            if dates_vols: jour_dep = int(dates_vols[0])
                            else:
                                jours = re.findall(r'\b(0?[1-9]|[12][0-9]|3[01])\b', line)
                                jour_dep = int(jours[0]) if jours else 1

                            # Doublon strict : Même mois + Même jour + Même destination IATA
                            doublon = any(
                                r['mois'] == current_month and r['jour_dep'] == jour_dep and r['arrivee'] == code 
                                for r in rotations
                            )

                            if not doublon:
                                info = REF_IATA[code]
                                km = dist_base * 2 if data_transport == 'Voiture' else 0
                                rotations.append({
                                    'mois': current_month, 'mode': 'LC',
                                    'jour_dep': jour_dep, 'jour_arr': jour_dep + 3,
                                    'arrivee': code, 'details': f"{code} ({info['ville']})",
                                    'nb_jours': 3, 'total': 3 * info['forfait'], 'km': km,
                                    'ville': info['ville'], 'pays': info['pays'], 'taux': info['forfait']
                                })
                page.flush_cache()

    except Exception as e:
        print(f"Erreur extraction rotations : {e}")

    # Nettoyage des kilomètres cumulés si plusieurs rotations partent le même jour
    if rotations:
        rotations.sort(key=lambda x: (LISTE_MOIS.index(x['mois']) if x['mois'] in LISTE_MOIS else 99, x['jour_dep']))
        for i in range(len(rotations) - 1):
            if rotations[i]['mois'] == rotations[i+1]['mois'] and rotations[i]['jour_dep'] == rotations[i+1]['jour_dep']:
                rotations[i+1]['km'] = 0  # Évite de compter deux fois le trajet domicile-base le même jour

    return rotations

