from datetime import timezone
from hashlib import md5
from io import BytesIO
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (DictionaryObject, NameObject, TextStringObject,
    ByteStringObject, NumberObject, ArrayObject, DecodedStreamObject)
from .xmp import ASSETS, PRODUCER, make_xmp
from .render import render


def dictionary(**items):
    return DictionaryObject({NameObject('/'+key): value for key, value in items.items()})


def assemble(invoice, xml, created_at, conformance='3b'):
    if conformance != '3b':
        raise NotImplementedError('Only 3b supported; 3a needs tagged rendering')
    if created_at.tzinfo is None:
        raise ValueError('Creation timestamp must include timezone')
    stamp = created_at.astimezone(timezone.utc).strftime("D:%Y%m%d%H%M%SZ")
    writer = PdfWriter(clone_from=BytesIO(render(invoice)))
    writer.pdf_header = '%PDF-1.7'
    writer.metadata.clear()
    writer.add_metadata({'/Title': 'Facture ' + invoice['invoice_number'],
                         '/Author': invoice['seller'].get('legal_name') or invoice['seller']['name'],
                         '/Creator': PRODUCER, '/Producer': PRODUCER,
                         '/CreationDate': stamp, '/ModDate': stamp})
    attachment = DecodedStreamObject()
    attachment.set_data(xml)
    attachment.update(dictionary(Type=NameObject('/EmbeddedFile'), Subtype=NameObject('/text/xml'),
        Params=dictionary(ModDate=TextStringObject(stamp), Size=NumberObject(len(xml)),
                          CheckSum=ByteStringObject(md5(xml, usedforsecurity=False).digest()))))
    attachment_ref = writer._add_object(attachment)
    spec = dictionary(Type=NameObject('/Filespec'), F=TextStringObject('factur-x.xml'),
        UF=TextStringObject('factur-x.xml'), Desc=TextStringObject('Facture structurée EN 16931'),
        AFRelationship=NameObject('/Alternative'), EF=dictionary(F=attachment_ref, UF=attachment_ref))
    spec_ref = writer._add_object(spec)
    writer.root_object[NameObject('/AF')] = ArrayObject([spec_ref])
    writer.root_object[NameObject('/Names')] = dictionary(EmbeddedFiles=dictionary(
        Names=ArrayObject([TextStringObject('factur-x.xml'), spec_ref])))
    metadata = DecodedStreamObject()
    metadata.set_data(make_xmp(invoice, created_at, conformance))
    metadata.update(dictionary(Type=NameObject('/Metadata'), Subtype=NameObject('/XML')))
    writer.root_object[NameObject('/Metadata')] = writer._add_object(metadata)
    icc = DecodedStreamObject()
    icc.set_data((ASSETS/'sRGB.icc').read_bytes())
    icc[NameObject('/N')] = NumberObject(3)
    intent = dictionary(Type=NameObject('/OutputIntent'), S=NameObject('/GTS_PDFA1'),
        OutputConditionIdentifier=TextStringObject('sRGB'), Info=TextStringObject('sRGB'),
        DestOutputProfile=writer._add_object(icc))
    writer.root_object[NameObject('/OutputIntents')] = ArrayObject([writer._add_object(intent)])
    writer.root_object[NameObject('/Lang')] = TextStringObject('fr-FR')
    writer.generate_file_identifiers()
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
