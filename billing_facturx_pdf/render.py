"""Readable representation of the explicit, unchanged CII input data."""
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from .xmp import ASSETS

INK = colors.HexColor('#183344')
TEAL = colors.HexColor('#0B6869')
PALE = colors.HexColor('#EEF5F4')


def render(invoice):
    for name, filename in [('FXRegular', 'Vera.ttf'), ('FXBold', 'VeraBd.ttf')]:
        pdfmetrics.registerFont(TTFont(name, str(ASSETS / filename)))
    pdfmetrics.registerFontFamily('FXRegular', normal='FXRegular', bold='FXBold')
    styles = {
        'body': ParagraphStyle('body', fontName='FXRegular', fontSize=8.4, leading=12, textColor=INK),
        'small': ParagraphStyle('small', fontName='FXRegular', fontSize=7.2, leading=10, textColor=INK),
        'title': ParagraphStyle('title', fontName='FXBold', fontSize=25, leading=30, textColor=INK),
        'h': ParagraphStyle('h', fontName='FXBold', fontSize=10, leading=15, textColor=TEAL),
    }
    def para(text, style='body'):
        return Paragraph(escape(str(text)), styles[style])
    story = []
    def add(text, style='body'):
        story.append(para(text, style))
    def section(text):
        story.append(Spacer(1, 12));add(text, 'h');story.append(Spacer(1, 5))
    kind = invoice['invoice_type']
    labels = {'normal': ('FACTURE', 'Facture normale', '380'),
              'deposit': ("FACTURE D'ACOMPTE", "Facture d'acompte", '386'),
              'balance': ('FACTURE DE SOLDE', 'Facture de solde', '380')}
    if kind not in labels or invoice['buyer']['type'] not in ('Entreprise', 'Particulier'):
        raise ValueError('Only B2B/B2C normal, deposit and balance are supported')
    title, label, code = labels[kind]
    add(title, 'title')
    add(invoice['invoice_number'], 'h')
    add('Date : ' + invoice['invoice_date'] + '   |   Devise : ' + invoice['currency'])
    if invoice.get('business_process_id'):
        add(label + ' (' + code + ') - Prestation de service déjà payée (' + invoice['business_process_id'] + ')', 'small')
    else:
        add(label + ' (' + code + ')', 'small')
    if invoice.get('quote', {}).get('quote_id'):
        add('Devis : ' + invoice['quote']['quote_id'] + ' (référence 916)', 'small')
    if invoice.get('deposit_reference'):
        ref = invoice['deposit_reference']
        add("Facture d'acompte : " + ref['invoice_number'] + ' du ' + ref['invoice_date'], 'small')
    section('Vendeur / Acheteur')
    def party(role):
        p = invoice[role]
        name = p['name'] if role == 'buyer' and invoice['buyer']['type'] == 'Particulier' else (p.get('legal_name') or p.get('company_name') or p['name'])
        rows = [name]
        # Include the legal/contact information actually serialized into CII.
        for key in ('address' if role == 'seller' else 'address_1', 'address_2'):
            if p.get(key): rows.append(p[key])
        rows.append(' '.join(str(p.get(k, '')) for k in ('postal_code', 'city', 'country')).strip())
        for key, label in [('phone','Téléphone'), ('email','Courriel')]:
            if p.get(key): rows.append(label + ' : ' + p[key])
        legal = p.get('siren') if role == 'seller' else p.get('siret')
        if legal: rows.append('SIREN (0002) : ' + legal[:9])
        if p.get('siret') and len(p['siret']) == 14: rows.append('SIRET (0009) : ' + p['siret'])
        if role == 'seller': rows.append('Identifiant fiscal (FC) : ' + p['siren'])
        if p.get('electronic_address'):
            endpoint = p['electronic_address']
            rows.append('Adresse de facturation (' + endpoint['scheme_id'] + ') : ' + endpoint['value'])
        return [para(line, 'small') for line in rows]
    t = Table([[party('seller'), party('buyer')]], colWidths=[251, 251])
    t.setStyle(TableStyle([('FONTNAME',(0,0),(-1,-1),'FXRegular'),('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,-1),PALE),
                          ('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),
                          ('TOPPADDING',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),9)]))
    story.append(t)
    section('Prestation facturée')
    line = invoice['lines'][0]
    cells = [['Ligne / Description', 'Quantité / unité', 'Prix HT', 'Total HT'],
             [str(line['line_number']) + ' / ' + line['description'],
              str(line['quantity']) + ' / ' + line['unit'],
              format(line['unit_price_ht'], '.2f'), format(line['line_total_ht'], '.2f')]]
    table = Table([[para(c, 'small') for c in row] for row in cells], colWidths=[220,110,86,86])
    table.setStyle(TableStyle([('FONTNAME',(0,0),(-1,-1),'FXRegular'),('BACKGROUND',(0,0),(-1,0),PALE),('TOPPADDING',(0,0),(-1,-1),7),
                              ('BOTTOMPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,-1),(-1,-1),.5,TEAL)]))
    story.append(table)
    tax = invoice['tax'];totals = invoice['totals']
    add('TVA : ' + str(tax['rate']) + ' % - catégorie ' + tax['category'] + ' (VAT)', 'small')
    add(tax['exemption_reason'])
    add('Motif : ' + tax['exemption_code'], 'small')
    section('Montants et règlement')
    for label, amount in [('Total HT des lignes',totals['total_ht']),('Base imposable',tax['taxable_amount']),
                          ('TVA',totals['vat_amount']),('Total TTC',totals['total_ttc']),
                          ('Montant déjà payé',totals['prepaid_amount']),('Net à payer',totals['payable_amount'])]:
        add(label + ' : ' + format(amount, '.2f') + ' ' + invoice['currency'])
    if invoice.get('payment_terms', {}).get('due_date'):
        add('Date de paiement / échéance : ' + invoice['payment_terms']['due_date'])
    if invoice.get('notes'):
        section('Conditions de paiement')
    for note in invoice.get('notes', []):
        add(note['subject_code'] + ' - ' + note['content'])
        story.append(Spacer(1, 3))
    section('Références de la facture électronique')
    if invoice.get('business_process_id'):
        add('Profil EN 16931 - Cadre de facturation : ' + invoice['business_process_id'], 'small')
    else:
        add('Profil EN 16931', 'small')
    add('Identifiant de profil : urn:cen.eu:en16931:2017', 'small')
    stream = BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=A4, leftMargin=46, rightMargin=46,
                            topMargin=37, bottomMargin=40)
    def canvasmaker(*args, **kwargs):
        kwargs.update(initialFontName='FXRegular', pdfVersion=(1,7))
        return Canvas(*args, **kwargs)
    def footer(canvas, doc):
        canvas.setFont('FXRegular', 7)
        canvas.setFillColor(INK)
        canvas.drawString(46, 24, invoice['invoice_number'] + ' | Factur-X - XML embarqué')
        canvas.drawRightString(A4[0]-46, 24, str(doc.page))
    doc.build(story, canvasmaker=canvasmaker, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()
