function escapeXml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function buildUblInvoiceXml(invoice) {
  if (!invoice) {
    throw new Error("Invoice data manquante");
  }

  const seller = invoice.seller || {};
  const buyer = invoice.buyer || {};
  const tax = invoice.tax || {};
  const totals = invoice.totals || {};
  const line = invoice.lines?.[0] || {};

  const currency = invoice.currency || "EUR";

 
  const dueDate =
  invoice.payment_date
    ? String(invoice.payment_date).slice(0, 10)
    : invoice.invoice_date;

  const invoiceTypeCode =
    invoice.invoice_type === "deposit"
      ? "386"
      : "380";

  const sellerName =
    seller.legal_name ||
    seller.name ||
    "";

  const buyerName =
    buyer.type === "Entreprise"
      ? buyer.company_name || buyer.name || ""
      : buyer.name || "";

  const sellerVatId =
    seller.vat_number || "";

  const buyerVatId =
    buyer.vat_number || "";

  const exemptionXml =
    tax.category === "E"
      ? `
        <cbc:TaxExemptionReasonCode>${escapeXml(
          tax.exemption_code
        )}</cbc:TaxExemptionReasonCode>
        <cbc:TaxExemptionReason>${escapeXml(
          tax.exemption_reason
        )}</cbc:TaxExemptionReason>`
      : "";

  const depositReferenceXml =
    invoice.deposit_reference?.invoice_number
      ? `
    <cac:AdditionalDocumentReference>
      <cbc:ID>${escapeXml(
        invoice.deposit_reference.invoice_number
      )}</cbc:ID>
    </cac:AdditionalDocumentReference>`
      : "";

  return `<?xml version="1.0" encoding="UTF-8"?>
<Invoice
  xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
  xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
  xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">

  <cbc:UBLVersionID>2.1</cbc:UBLVersionID>

  <cbc:CustomizationID>urn:cen.eu:en16931:2017</cbc:CustomizationID>
  <cbc:ProfileID>S2</cbc:ProfileID>

  <cbc:ID>${escapeXml(invoice.invoice_number)}</cbc:ID>

  <cbc:IssueDate>${escapeXml(invoice.invoice_date)}</cbc:IssueDate>

  <cbc:DueDate>${escapeXml(dueDate)}</cbc:DueDate>

  <cbc:InvoiceTypeCode>${invoiceTypeCode}</cbc:InvoiceTypeCode>
  <cbc:Note>#PMT# Indemnité forfaitaire pour frais de recouvrement : 40 EUR en cas de retard de paiement.</cbc:Note>

  <cbc:Note>#PMD# Pénalités de retard exigibles en cas de paiement tardif selon les conditions contractuelles applicables.</cbc:Note>

  <cbc:Note>#AAB# Aucun escompte accordé pour paiement anticipé.</cbc:Note>

  <cbc:DocumentCurrencyCode>${escapeXml(currency)}</cbc:DocumentCurrencyCode>

  ${depositReferenceXml}

  <cac:AccountingSupplierParty>
    <cac:Party>

      <cbc:EndpointID schemeID="0225">${escapeXml(
        seller.siren
      )}</cbc:EndpointID>
    

      <cac:PartyIdentification>
      <cbc:ID schemeID="0009">${escapeXml(
        seller.siret || seller.siren
      )}</cbc:ID>
    </cac:PartyIdentification>

      <cac:PartyName>
        <cbc:Name>${escapeXml(sellerName)}</cbc:Name>
      </cac:PartyName>

      <cac:PostalAddress>
        <cbc:StreetName>${escapeXml(seller.address)}</cbc:StreetName>
        <cbc:CityName>${escapeXml(seller.city)}</cbc:CityName>
        <cbc:PostalZone>${escapeXml(seller.postal_code)}</cbc:PostalZone>

        <cac:Country>
          <cbc:IdentificationCode>${escapeXml(
            seller.country || "FR"
          )}</cbc:IdentificationCode>
        </cac:Country>
      </cac:PostalAddress>

      ${
        sellerVatId
          ? `
            <cac:PartyTaxScheme>
              <cbc:CompanyID>${escapeXml(sellerVatId)}</cbc:CompanyID>
              <cac:TaxScheme>
                <cbc:ID>VAT</cbc:ID>
              </cac:TaxScheme>
            </cac:PartyTaxScheme>`
          : `
            <cac:PartyTaxScheme>
              <cbc:CompanyID>${escapeXml(
                seller.siret || seller.siren
              )}</cbc:CompanyID>
              <cac:TaxScheme>
                <cbc:ID>FC</cbc:ID>
              </cac:TaxScheme>
            </cac:PartyTaxScheme>`
      }

      <cac:PartyLegalEntity>
      <cbc:RegistrationName>${escapeXml(sellerName)}</cbc:RegistrationName>
      <cbc:CompanyID schemeID="0002">${escapeXml(
        seller.siren
      )}</cbc:CompanyID>
    </cac:PartyLegalEntity>

      <cac:Contact>
        <cbc:Telephone>${escapeXml(seller.phone)}</cbc:Telephone>
        <cbc:ElectronicMail>${escapeXml(seller.email)}</cbc:ElectronicMail>
      </cac:Contact>

    </cac:Party>
  </cac:AccountingSupplierParty>

  <cac:AccountingCustomerParty>
    <cac:Party>
    ${
      String(buyer.type || "").toLowerCase() === "particulier"
        ? `<cbc:EndpointID schemeID="EM">${escapeXml(buyer.email)}</cbc:EndpointID>`
        : `<cbc:EndpointID schemeID="0225">${escapeXml(
            String(buyer.siret || "").slice(0, 9)
          )}</cbc:EndpointID>`
    }

      <cac:PartyName>
        <cbc:Name>${escapeXml(buyerName)}</cbc:Name>
      </cac:PartyName>

      <cac:PostalAddress>
        <cbc:StreetName>${escapeXml(buyer.address_1)}</cbc:StreetName>

        ${
          buyer.address_2
            ? `<cbc:AdditionalStreetName>${escapeXml(
                buyer.address_2
              )}</cbc:AdditionalStreetName>`
            : ""
        }

        <cbc:CityName>${escapeXml(buyer.city)}</cbc:CityName>
        <cbc:PostalZone>${escapeXml(buyer.postal_code)}</cbc:PostalZone>

        <cac:Country>
          <cbc:IdentificationCode>${escapeXml(
            buyer.country || "FR"
          )}</cbc:IdentificationCode>
        </cac:Country>
      </cac:PostalAddress>

      ${
        buyerVatId
          ? `
      <cac:PartyTaxScheme>
        <cbc:CompanyID>${escapeXml(buyerVatId)}</cbc:CompanyID>

        <cac:TaxScheme>
          <cbc:ID>VAT</cbc:ID>
        </cac:TaxScheme>
      </cac:PartyTaxScheme>`
          : ""
      }

      <cac:PartyLegalEntity>
        <cbc:RegistrationName>${escapeXml(buyerName)}</cbc:RegistrationName>

        ${
          buyer.siret
            ? `<cbc:CompanyID>${escapeXml(buyer.siret)}</cbc:CompanyID>`
            : ""
        }
      </cac:PartyLegalEntity>

      <cac:Contact>
        <cbc:Telephone>${escapeXml(buyer.phone)}</cbc:Telephone>
        <cbc:ElectronicMail>${escapeXml(buyer.email)}</cbc:ElectronicMail>
      </cac:Contact>

    </cac:Party>
  </cac:AccountingCustomerParty>

  <cac:TaxTotal>

    <cbc:TaxAmount currencyID="${escapeXml(currency)}">${Number(
      tax.tax_amount || 0
    ).toFixed(2)}</cbc:TaxAmount>

    <cac:TaxSubtotal>

      <cbc:TaxableAmount currencyID="${escapeXml(currency)}">${Number(
        tax.taxable_amount || 0
      ).toFixed(2)}</cbc:TaxableAmount>

      <cbc:TaxAmount currencyID="${escapeXml(currency)}">${Number(
        tax.tax_amount || 0
      ).toFixed(2)}</cbc:TaxAmount>

      <cac:TaxCategory>

        <cbc:ID>${escapeXml(tax.category)}</cbc:ID>

        <cbc:Percent>${Number(
          tax.rate || 0
        ).toFixed(2)}</cbc:Percent>

        ${exemptionXml}

        <cac:TaxScheme>
          <cbc:ID>VAT</cbc:ID>
        </cac:TaxScheme>

      </cac:TaxCategory>

    </cac:TaxSubtotal>

  </cac:TaxTotal>

  <cac:LegalMonetaryTotal>

    <cbc:LineExtensionAmount currencyID="${escapeXml(currency)}">${Number(
      totals.total_ht || 0
    ).toFixed(2)}</cbc:LineExtensionAmount>

    <cbc:TaxExclusiveAmount currencyID="${escapeXml(currency)}">${Number(
      totals.total_ht || 0
    ).toFixed(2)}</cbc:TaxExclusiveAmount>

    <cbc:TaxInclusiveAmount currencyID="${escapeXml(currency)}">${Number(
      totals.total_ttc || 0
    ).toFixed(2)}</cbc:TaxInclusiveAmount>

    <cbc:PrepaidAmount currencyID="${escapeXml(currency)}">${Number(
      totals.prepaid_amount || 0
    ).toFixed(2)}</cbc:PrepaidAmount>

    <cbc:PayableAmount currencyID="${escapeXml(currency)}">${Number(
      totals.payable_amount || 0
    ).toFixed(2)}</cbc:PayableAmount>

  </cac:LegalMonetaryTotal>

  <cac:InvoiceLine>

    <cbc:ID>${escapeXml(line.line_number || 1)}</cbc:ID>

    <cbc:InvoicedQuantity unitCode="${escapeXml(
      line.unit || "C62"
    )}">${Number(line.quantity || 1)}</cbc:InvoicedQuantity>

    <cbc:LineExtensionAmount currencyID="${escapeXml(currency)}">${Number(
      line.line_total_ht || 0
    ).toFixed(2)}</cbc:LineExtensionAmount>

    <cac:Item>

      <cbc:Name>${escapeXml(line.description)}</cbc:Name>

      <cac:ClassifiedTaxCategory>

        <cbc:ID>${escapeXml(line.tax_category)}</cbc:ID>

        <cbc:Percent>${Number(
          line.vat_rate || 0
        ).toFixed(2)}</cbc:Percent>

        <cac:TaxScheme>
          <cbc:ID>VAT</cbc:ID>
        </cac:TaxScheme>

      </cac:ClassifiedTaxCategory>

    </cac:Item>

    <cac:Price>
      <cbc:PriceAmount currencyID="${escapeXml(currency)}">${Number(
        line.unit_price_ht || 0
      ).toFixed(2)}</cbc:PriceAmount>
    </cac:Price>

  </cac:InvoiceLine>

</Invoice>`;
}
module.exports = { buildUblInvoiceXml };
