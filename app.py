from flask import Flask, request, render_template
import json
import socket
from datetime import datetime
import csv
import os
import re
import pdfplumber
import io
import zipfile
import fitz  # C'est le nom de PyMuPDF
app = Flask(__name__)
import re

# ==========================================
# 1. CHARGEMENT DES DICTIONNAIRES (CSV)
# ==========================================
CSV_IATA_NAME = 'data_indemnites.CSV'
CSV_ACTIVITES_NAME = 'codes_activites.CSV'

def charger_iata_csv(nom_fichier):
    donnees = {}
    chemin = os.path.join(os.path.dirname(os.path.abspath(__file__)), nom_fichier)
    if not os.path.exists(chemin): return {}
    try:
        with open(chemin, mode='r', encoding='utf-8-sig', errors='ignore') as f:
            content = f.read()
        delimiter = ';' if ';' in content else ','
        reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
        for row in reader:
            clean_row = {str(k).strip().upper(): str(v).strip() for k, v in row.items() if k is not None}
            code = clean_row.get('CODE_IATA', '')
            if code and len(code) == 3:
                montant = clean_row.get('MONTANT', '0').replace(',', '.').replace('€', '').replace(' ', '')
                try:
                    donnees[code.upper()] = {
                        "ville": clean_row.get('VILLE', code), 
                        "pays": clean_row.get('PAYS', '-'), 
                        "forfait": float(montant)
                    }
                except ValueError: continue
    except Exception as e: print(f"Erreur lecture IATA: {e}")
    return donnees

def charger_activites_csv(nom_fichier):
    donnees = {}
    chemin = os.path.join(os.path.dirname(os.path.abspath(__file__)), nom_fichier)
    if not os.path.exists(chemin): return {}
    try:
        with open(chemin, mode='r', encoding='utf-8-sig', errors='ignore') as f:
            content = f.read()
        delimiter = ';' if ';' in content else ','
        reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
        for row in reader:
            clean_row = {str(k).strip().upper(): str(v).strip() for k, v in row.items() if k is not None}
            code = clean_row.get('CODE', '')
            if code and len(code) == 3:
                donnees[code.upper()] = {
                    "categorie": clean_row.get('CATEGORIE', 'SOL'),
                    "libelle": clean_row.get('LIBELLE', 'Activité Sol'),
                    "genere_km": clean_row.get('GENERE_KM', 'NON').upper()
                }
    except Exception as e: print(f"Erreur lecture Activités: {e}")
    return donnees

REF_IATA = charger_iata_csv(CSV_IATA_NAME)
REF_ACTIVITES = charger_activites_csv(CSV_ACTIVITES_NAME)

# ==========================================
# 2. CONFIGURATION ET UTILITAIRES
# ==========================================
LISTE_MOIS = ["Janvier", "Fevrier", "Mars", "Avril", "Mai", "Juin", "Juillet", "Aout", "Septembre", "Octobre", "Novembre", "Decembre"]
TAUX_FRANCE_MC = 55.0

def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try: s.connect(('10.255.255.255', 1)); ip = s.getsockname()[0]
    except Exception: ip = '127.0.0.1'
    finally: s.close()
    return ip

def clean_montant(val_str):
    if not val_str: return 0.0
    try:
        clean = re.sub(r'[^\d,\.-]', '', str(val_str)).replace(',', '.')
        if clean.count('.') > 1: 
            parts = clean.split('.')
            clean = "".join(parts[:-1]) + '.' + parts[-1]
        return float(clean)
    except: return 0.0

def calculer_frais_km(cv, distance):
    d = float(distance)
    if d == 0: return 0
    p = max(min(int(cv), 7), 3) 
    if p == 3: return d * 0.529 if d <= 5000 else (d * 0.316) + 1065 if d <= 20000 else d * 0.370
    elif p == 4: return d * 0.606 if d <= 5000 else (d * 0.340) + 1330 if d <= 20000 else d * 0.407
    elif p == 5: return d * 0.636 if d <= 5000 else (d * 0.357) + 1395 if d <= 20000 else d * 0.427
    elif p == 6: return d * 0.665 if d <= 5000 else (d * 0.374) + 1457 if d <= 20000 else d * 0.447
    elif p >= 7: return d * 0.697 if d <= 5000 else (d * 0.394) + 1515 if d <= 20000 else d * 0.470
    return 0

# ==========================================
# 3. MOTEUR D'EXTRACTION PDF
# ==========================================

def extraire_donnees_pdf(pdf_file):
    resultats = {} 
    try:
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                text = page.extract_text(layout=False)
                if not text:
                    page.flush_cache()
                    continue
                text_upper = text.upper()
                mois_page = "INCONNU"
                
                match_periode = re.search(r"PERIODE\s+DU\s+\d{2}/(\d{2})/\d{4}", text_upper)
                if match_periode:
                    try:
                        idx = int(match_periode.group(1)) - 1
                        if 0 <= idx < 12: mois_page = LISTE_MOIS[idx]
                    except: pass
                if mois_page == "INCONNU":
                    for m in LISTE_MOIS:
                        if re.search(rf"\b{m.upper()}\b", text_upper): mois_page = m; break
                
                if mois_page == "INCONNU":
                    page.flush_cache()
                    continue
                if mois_page not in resultats: resultats[mois_page] = {'net': 0.0, 'ind_non': 0.0, 'ind_imp': 0.0, 'trans': 0.0}

                for line in text_upper.split('\n'):
                    clean_line = line.strip()
                    if "NET A PAYER AVANT IMPÔT" in clean_line:
                        m = re.findall(r"([\d\s]+[.,]\d{2})", clean_line)
                        if m: 
                            val = clean_montant(m[-1])
                            if val > 500: resultats[mois_page]['net'] = val
                    elif any(k in clean_line for k in ["IR EXON", "IND REPAS", "IND.REPAS", "PRIME REPAS"]) and "NON EXON" not in clean_line:
                        m = re.findall(r"([\d\s]+[.,]\d{2})", clean_line)
                        if m: resultats[mois_page]['ind_non'] += clean_montant(m[-1])
                    elif "IR NON EXON" in clean_line:
                        m = re.findall(r"([\d\s]+[.,]\d{2})", clean_line)
                        if m: resultats[mois_page]['ind_imp'] += clean_montant(m[-1])
                    elif "FRAIS REELS TRANSP" in clean_line or "IND KILOM" in clean_line:
                        m = re.findall(r"([\d\s]+[.,]\d{2})", clean_line)
                        if m: resultats[mois_page]['trans'] += clean_montant(m[-1])
                page.flush_cache()
    except Exception as e: print(f"Erreur Paie PDF: {e}")
    return resultats

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
                
                lignes_utiles = []
                for l in text_upper.split('\n'):
                    ligne_propre = l.replace(" ", "").replace("É", "E").replace("È", "E").replace("Û", "U")
                    if "CUMUL" in ligne_propre:
                        continue
                    lignes_utiles.append(l)
                
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
                            
                        if code in REF_ACTIVITES:
                            dates_vols = re.findall(r'\b(0?[1-9]|[12][0-9]|3[01])\s*(?:\|)?\s*(?:[01][0-9]|2[0-3])[.:][0-9]{2}\b', line)
                            if dates_vols: jour_dep = int(dates_vols[0])
                            else:
                                jours = re.findall(r'\b(0?[1-9]|[12][0-9]|3[01])\b', line)
                                jour_dep = int(jours[0]) if jours else 1
                            
                            doublon = False
                            for r in rotations:
                                if r['mois'] == current_month and r['arrivee'] == code and r['jour_dep'] == jour_dep:
                                    doublon = True
                                    break
                                    
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
                                
                        elif code in REF_IATA and code not in EXCLUSIONS:
                            dates_vols = re.findall(r'\b(0?[1-9]|[12][0-9]|3[01])\s*(?:\|)?\s*(?:[01][0-9]|2[0-3])[.:][0-9]{2}\b', line)
                            if dates_vols: jour_dep = int(dates_vols[0])
                            else:
                                jours = re.findall(r'\b(0?[1-9]|[12][0-9]|3[01])\b', line)
                                jour_dep = int(jours[0]) if jours else 1
                            
                            doublon = False
                            for r in rotations:
                                if r['mois'] == current_month and r['arrivee'] == code and abs(r['jour_dep'] - jour_dep) <= 4:
                                    doublon = True
                                    break
                            
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

    if rotations:
        rotations.sort(key=lambda x: x['jour_dep'])
        for i in range(len(rotations) - 1):
            ligne_actuelle = rotations[i]
            ligne_suivante = rotations[i+1]
            if ligne_actuelle['jour_dep'] == ligne_suivante['jour_dep']:
                ligne_actuelle['km'] = 0
    return rotations

def extraire_montant_attestation(pdf_file):
    try:
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                text = page.extract_text(layout=False)
                if not text:
                    page.flush_cache()
                    continue
                titre_cible = r"ATTESTATION DE DECOMPTE DES NUITEES POUR L'ANNEE"
                if re.search(titre_cible, text, re.IGNORECASE):
                    match = re.search(r"s'élève à\s*([\d\s]+[.,]\d{2})", text, re.IGNORECASE)
                    if match:
                        montant_final = clean_montant(match.group(1))
                        page.flush_cache()
                        return montant_final
                page.flush_cache()
    except Exception as e:
        print(f"Erreur lors de l'extraction de l'attestation : {e}")
    return 0.0
from fpdf import FPDF

def generer_pdf_final(data, revenus, lignes):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    
    # Titre
    pdf.cell(190, 10, f"DECLARATION FRAIS REELS - {data.get('annee', '2024')}", ln=True, align='C')
    pdf.ln(10)
    
    # Infos PNC
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(190, 10, f"Personnel Navigant : {data.get('prenom')} {data.get('nom')}", ln=True)
    pdf.set_font("Arial", '', 11)
    pdf.cell(190, 7, f"Fonction : {data.get('fonction')} | Base : {data.get('base')}", ln=True)
    pdf.ln(5)

    # Recapitulatif Financier
    pdf.set_fill_color(230, 230, 230)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(190, 10, " RECAPITULATIF DES CALCULS", ln=True, fill=True)
    pdf.set_font("Arial", '', 11)
    
    # Calculs (on utilise les totaux que tu calcules déjà dans l'index)
    total_indem = sum(l.get('total', 0) for l in lignes)
    total_km_val = 0 # À lier à ta fonction calculer_frais_km
    
    pdf.cell(100, 8, "Total Indemnites de repas (Rotations) :", border=0)
    pdf.cell(90, 8, f"{total_indem:,.2f} EUR", border=0, ln=True, align='R')
    
    pdf.cell(100, 8, "Total Frais Kilometriques :", border=0)
    pdf.cell(90, 8, f"{data.get('total_km_valeur', 0):,.2f} EUR", border=0, ln=True, align='R')
    
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 14)
    grand_total = total_indem + float(data.get('total_km_valeur', 0)) + float(data.get('total_frais_divers', 0))
    pdf.cell(100, 10, "TOTAL GENERAL A DECLARER :")
    pdf.cell(90, 10, f"{grand_total:,.2f} EUR", ln=True, align='R')

    # Retourne le PDF sous forme de bytes
    return pdf.output(dest='S').encode('latin-1')
@app.route('/', methods=['GET', 'POST'])
def index():
    step = 'login'
    data, revenus, lignes = {}, [], []
    error_rotation = None
    upload_error = False 
    today = datetime.now().strftime("%d/%m/%Y")
    form_state, revenu_form_state = {}, {}
    last_edited_month = None

    if request.method == 'POST':
        action = request.form.get('action')
        if request.form.get('current_data'): data = json.loads(request.form.get('current_data'))
        if request.form.get('current_revenus'): revenus = json.loads(request.form.get('current_revenus'))
        if request.form.get('current_lignes'): lignes = json.loads(request.form.get('current_lignes'))

        if action == 'do_login': step = 0 
        elif action == 'logout': step = 'login'
        elif action == 'go_register': step = 'register'
        elif action == 'do_register': step = 0
        elif action == 'nav_click': step = int(request.form.get('target_step'))

        elif action == 'save_step_1':
            for key in ['annee', 'nom', 'prenom', 'fonction', 'base', 'regime', 'email', 'num_fiscal', 'adr_rue', 'adr_cp', 'adr_ville', 'transport_mode', 'dist_base', 'cv']:
                data[key] = request.form.get(key)
            if data.get('nom'): data['nom'] = data['nom'].upper()
            mode_transp = data.get('transport_mode')
            dist_b = float(data.get('dist_base') or 0)
            for l in lignes:
                if mode_transp == 'Voiture':
                    code = l.get('arrivee', '')
                    if code in REF_ACTIVITES:
                        if REF_ACTIVITES[code].get('genere_km') == 'OUI':
                            l['km'] = dist_b * 2 * l.get('nb_jours', 1)
                        else: l['km'] = 0
                    elif l.get('mode') in ['SOL', 'RESERVE']:
                        l['km'] = dist_b * 2 * l.get('nb_jours', 1)
                    else: l['km'] = dist_b * 2
                else: l['km'] = 0
            step = 2
            
        elif action == 'delete_revenu':
            try: del revenus[int(request.form.get('line_index'))]
            except: pass
            step = 3

        elif action == 'edit_revenu':
            try: revenu_form_state = revenus.pop(int(request.form.get('line_index')))
            except: pass
            step = 3

        elif action == 'upload_pdf':
            if 'pdf_file' in request.files:
                fichiers = request.files.getlist('pdf_file')
                for f in fichiers:
                    if f.filename == '': continue
                    file_content = f.read()
                    pdf_list = []
                    if f.filename.lower().endswith('.zip'):
                        with zipfile.ZipFile(io.BytesIO(file_content)) as thezip:
                            for zipinfo in thezip.infolist():
                                if zipinfo.filename.lower().endswith('.pdf'):
                                    with thezip.open(zipinfo) as thefile: pdf_list.append(io.BytesIO(thefile.read()))
                    else: pdf_list.append(io.BytesIO(file_content))
                    for pdf_io in pdf_list:
                        extracted = extraire_donnees_pdf(pdf_io)
                        if not extracted: upload_error = True
                        else:
                            existing_months = [r['mois'] for r in revenus]
                            for mois, vals in extracted.items():
                                if mois not in existing_months:
                                    vals['mois'] = mois
                                    vals['total'] = vals['net'] + vals['ind_imp'] + vals['ind_non'] + vals['trans']
                                    revenus.append(vals)
                            revenus.sort(key=lambda x: [m.upper() for m in LISTE_MOIS].index(str(x['mois']).upper().strip()) if str(x['mois']).upper().strip() in [m.upper() for m in LISTE_MOIS] else 99)
            step = 3

        elif action == 'upload_ep4':
            if 'pdf_file' in request.files:
                fichiers = request.files.getlist('pdf_file')
                for f in fichiers:
                    if f.filename == '': continue
                    file_content = f.read()
                    pdf_list = []
                    if f.filename.lower().endswith('.zip'):
                        with zipfile.ZipFile(io.BytesIO(file_content)) as thezip:
                            for zipinfo in thezip.infolist():
                                if zipinfo.filename.lower().endswith('.pdf'):
                                    with thezip.open(zipinfo) as thefile: pdf_list.append(io.BytesIO(thefile.read()))
                    else: pdf_list.append(io.BytesIO(file_content))
                    for pdf_io in pdf_list:
                        mode_transp = data.get('transport_mode')
                        dist_b = float(data.get('dist_base') or 0)
                        rots = extraire_rotations_pdf(pdf_io, mode_transp, dist_b)
                        if rots: lignes.extend(rots)
                        pdf_io.seek(0)
                        att_val = extraire_montant_attestation(pdf_io)
                        if att_val > 0: data['montant_attestation'] = att_val
                    lignes.sort(key=lambda x: (LISTE_MOIS.index(x['mois']) if x['mois'] in LISTE_MOIS else 99, x['jour_dep']))
            step = 2

        elif action == 'add_rotation':
            try:
                mois_act = request.form.get('mois_act')
                regime_ligne = request.form.get('mode_act', 'LC')
                j_dep = int(request.form.get('jour_dep'))
                j_arr = int(request.form.get('jour_arr'))
                nb_jours = (j_arr - j_dep + 1) if j_arr >= j_dep else (31 - j_dep + j_arr + 1)
                if nb_jours < 1: nb_jours = 1
                if regime_ligne in ['SOL', 'RESERVE']:
                    km = float(data.get('dist_base') or 0) * 2 * nb_jours if (data.get('transport_mode') == 'Voiture' and regime_ligne == 'SOL') else 0
                    lignes.append({'mois': mois_act, 'mode': regime_ligne, 'jour_dep': j_dep, 'jour_arr': j_arr, 'arrivee': regime_ligne, 'details': f"Activité {regime_ligne.capitalize()}", 'nb_jours': nb_jours, 'total': 0.0, 'km': km, 'ville': 'Base', 'pays': 'France', 'taux': 0.0})
                elif regime_ligne == 'MC':
                    total_rotation = 0
                    escales_data = [] 
                    if nb_jours == 1:
                        total_rotation = 0.5 * TAUX_FRANCE_MC
                        escales_data.append({'etape': 'Journée', 'code': 'FR', 'ville': 'France', 'pays': '-', 'taux': TAUX_FRANCE_MC, 'coef': 0.5, 'total': total_rotation})
                    else:
                        nb_nuits = min(nb_jours - 1, 3)
                        for i in range(1, nb_nuits + 1):
                            iata_code = request.form.get(f'iata_{i}', '').strip().upper()
                            info = REF_IATA.get(iata_code, {"ville": "Inconnue", "pays": "-", "forfait": 150.0})
                            coef = 1.5 if i == nb_nuits else 1.0
                            amount = coef * info['forfait']
                            total_rotation += amount
                            escales_data.append({'etape': f'Nuit {i}', 'code': iata_code, 'ville': info['ville'], 'pays': info['pays'], 'taux': info['forfait'], 'coef': coef, 'total': amount})
                    km = float(data.get('dist_base') or 0) * 2 if data.get('transport_mode') == 'Voiture' else 0
                    lignes.append({'mois': mois_act, 'mode': 'MC', 'jour_dep': j_dep, 'jour_arr': j_arr, 'escales': escales_data, 'nb_jours': nb_jours, 'total': total_rotation, 'km': km, 'ville': 'Multi', 'pays': 'Zone Euro', 'taux': TAUX_FRANCE_MC})
                else: 
                    code = request.form.get('iata_arrivee', '').strip().upper()
                    if code in REF_IATA:
                        info = REF_IATA[code]
                        km = float(data.get('dist_base') or 0) * 2 if data.get('transport_mode') == 'Voiture' else 0
                        lignes.append({'mois': mois_act, 'mode': 'LC', 'jour_dep': j_dep, 'jour_arr': j_arr, 'arrivee': code, 'details': f"{code} ({info['ville']})", 'nb_jours': nb_jours, 'total': nb_jours * info['forfait'], 'km': km, 'ville': info['ville'], 'pays': info['pays'], 'taux': info['forfait']})
                lignes.sort(key=lambda x: (LISTE_MOIS.index(x['mois']), x['jour_dep']))
            except Exception as e: error_rotation = "Erreur de saisie."
            step = 2
        
        elif action == 'edit_rotation':
            try:
                item = lignes.pop(int(request.form.get('line_index')))
                form_state = {'mois_act': item['mois'], 'mode_act': item.get('mode', 'LC'), 'jour_dep': item['jour_dep'], 'jour_arr': item['jour_arr']}
                if item.get('mode') == 'LC': form_state['iata_arrivee'] = item.get('arrivee', '')
                elif item.get('mode') == 'MC' and item.get('escales'):
                    for esc in item['escales']:
                        if 'Nuit 1' in esc['etape']: form_state['iata_1'] = esc['code']
                        if 'Nuit 2' in esc['etape']: form_state['iata_2'] = esc['code']
                        if 'Nuit 3' in esc['etape']: form_state['iata_3'] = esc['code']
            except: pass
            step = 2
        elif action == 'delete_rotation':
            try: del lignes[int(request.form.get('line_index'))]
            except: pass
            step = 2
        elif action == 'clear_rotations':
            lignes = []
            step = 2
        elif action == 'view_report':
            data['cotis'] = float(request.form.get('cotis') or 0)
            data['uniforme'] = float(request.form.get('uniforme') or 0)
            data['bureau'] = float(request.form.get('bureau') or 0)
            data['autre'] = float(request.form.get('autre') or 0)
            val_att = request.form.get('montant_attestation')
            if val_att is not None: data['montant_attestation'] = float(val_att or 0)
            data['total_frais_divers'] = data['cotis'] + data['uniforme'] + data['bureau'] + data['autre']
            step = 5
        elif action == 'validate_force': step = 6 
        elif action == 'cancel_back': step = 4 

    total_jours = sum(l.get('nb_jours', 0) for l in lignes)
    total_indemnite_rotations = sum(l.get('total', 0) for l in lignes)
    total_km_annee = sum(l.get('km', 0) for l in lignes)
    total_km_valeur = 0
    if data.get('transport_mode') == 'Voiture' and data.get('cv'): total_km_valeur = calculer_frais_km(data.get('cv'), total_km_annee)
    sum_net = sum(r['net'] for r in revenus); sum_ind_imp = sum(r['ind_imp'] for r in revenus)
    sum_ind_non = sum(r['ind_non'] for r in revenus); sum_trans = sum(r['trans'] for r in revenus)
    total_rev_global = sum(r['total'] for r in revenus); total_revenus = total_rev_global + float(data.get('montant_attestation', 0.0))
    grand_total = total_indemnite_rotations + total_km_valeur + float(data.get('total_frais_divers', 0))
    months_count = len(set(l['mois'] for l in lignes))
    next_month_rev = LISTE_MOIS[0]; next_month_act = LISTE_MOIS[0]
    if revenus:
        try: next_month_rev = LISTE_MOIS[LISTE_MOIS.index(revenus[-1]['mois'])+1] if LISTE_MOIS.index(revenus[-1]['mois'])+1 < 12 else LISTE_MOIS[0]
        except: pass
    if lignes:
        try: next_month_act = LISTE_MOIS[LISTE_MOIS.index(lignes[-1]['mois'])] 
        except: pass
    if revenu_form_state: next_month_rev = revenu_form_state.get('mois')
    try:
        csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), CSV_IATA_NAME)
        date_bareme = datetime.fromtimestamp(os.path.getmtime(csv_path)).strftime('%d/%m/%Y')
    except: date_bareme = "Inconnue"

    return render_template('index.html', 
                           step=step, data=data, revenus=revenus, lignes=lignes, 
                           form_state=form_state, revenu_form_state=revenu_form_state, upload_error=upload_error,
                           total_jours=total_jours, total_indemnite_rotations=total_indemnite_rotations,
                           total_revenus=total_revenus, count_rev=len(revenus),
                           total_km_annee=total_km_annee, total_km_valeur=total_km_valeur, 
                           months_count=months_count, total_rev_net=sum_net, total_rev_ind_imp=sum_ind_imp,
                           total_rev_ind_non=sum_ind_non, total_rev_trans=sum_trans, total_rev_global=total_rev_global,
                           taken_months_rev=[r['mois'] for r in revenus], next_month_rev=next_month_rev,
                           next_month_act=next_month_act, error_rotation=error_rotation,
                           grand_total=grand_total, today=today, date_bareme=date_bareme,
                           last_edited_month=last_edited_month, sum_net=sum_net, sum_ind_imp=sum_ind_imp, 
                           sum_ind_non=sum_ind_non, sum_trans=sum_trans, all_months=LISTE_MOIS,
                           data_json=json.dumps(data), revenus_json=json.dumps(revenus), lignes_json=json.dumps(lignes))

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=False, port=5000)
