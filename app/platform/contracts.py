"""Generate immutable contract bytes from a versioned, canonical payload."""
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle

def render_contract(content,digest):
    stream=BytesIO();styles=getSampleStyleSheet()
    doc=SimpleDocTemplate(stream,pagesize=(8.5*inch,11*inch),rightMargin=42,leftMargin=42,topMargin=42,bottomMargin=42)
    story=[Paragraph('Ajo - Contribution agreement',styles['Title']),
           Paragraph(escape(content['name']),styles['Heading2']),
           Paragraph(f"Version {content['version']} | {content['currency']} | amounts in minor units",styles['Normal']),
           Spacer(1,12),Paragraph(escape(content['policy']['terms']),styles['Normal']),Spacer(1,12),
           Paragraph('Policy and integrity',styles['Heading2']),
           Paragraph('Canonical content SHA-256: '+digest,styles['Normal']),
           Paragraph(f"Policy version: {content['policy_version']}. No member may alter the frozen obligations unilaterally.",styles['Normal']),
           Paragraph('Participant payout order',styles['Heading2'])]
    for i,user in enumerate(content['members']):
        story.append(Paragraph(f"{i+1}. {escape(user['pseudonym'])}",styles['Normal']))
    story += [Paragraph('Contracted schedule',styles['Heading2'])]
    names={m['id']:m['pseudonym'] for m in content['members']}
    data=[['Due date','Member','Type','Amount']]
    for row in content['schedule']:
        data.append([row['date'],Paragraph(escape(names[row['user_id']]),styles['Normal']),row['kind'],f"{row['amount_minor']:,}"])
    table=LongTable(data,colWidths=[75,215,100,90],repeatRows=1)
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#164f43')),('TEXTCOLOR',(0,0),(-1,0),colors.white),
                               ('VALIGN',(0,0),(-1,-1),'TOP'),('FONTSIZE',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),7),
                               ('LINEBELOW',(0,0),(-1,-1),0.3,colors.HexColor('#dddddd'))]))
    story.append(table)
    def footer(canvas,document):
        canvas.setFont('Helvetica',8);canvas.drawString(42,24,f"Ajo | Agreement v{content['version']} | Page {document.page}")
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return stream.getvalue()
