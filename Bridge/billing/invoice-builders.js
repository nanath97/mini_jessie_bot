function createInvoiceBuilders({ base, getSellerConfig }) {
async function buildNormalInvoiceData(paymentFields, sellerSlug) {
  try {
    // =========================
    // 1. VÉRIFIER LE PAIEMENT
    // =========================
    const quoteId = String(
      paymentFields["Quote ID"] || ""
    ).trim();

    const paymentRole = String(
      paymentFields["Payment Role"] || ""
    ).trim();

    // Cette fonction ne traite QUE les paiements normaux
    if (quoteId || paymentRole) {
      throw new Error(
        "Paiement lié à un devis : buildNormalInvoiceData refusé"
      );
    }

    // =========================
    // 2. CHARGER LE VENDEUR
    // =========================
    const sellerConfig = await getSellerConfig(sellerSlug);

    if (!sellerConfig?.company) {
      throw new Error(
        `Configuration vendeur introuvable : ${sellerSlug}`
      );
    }

    const company = sellerConfig.company;

    // =========================
    // 3. MONTANT PAYÉ = TTC
    // =========================
    const amountCents = Number(
      paymentFields["Amount Cents"] || 0
    );

    if (!Number.isFinite(amountCents) || amountCents <= 0) {
      throw new Error("Amount Cents invalide");
    }

    const totalTtc = amountCents / 100;

    // =========================
    // 4. TVA
    // =========================
    const vatStatus = String(
      company.vat_status || ""
    ).trim();

    const vatRate = Number(
      company.default_vat_rate || 0
    );

    let totalHt;
    let vatAmount;

    let taxCategory;
    let taxExemptionCode = "";
    let taxExemptionReason = "";

    // Franchise en base
    if (vatStatus === "franchise_base") {
      totalHt = totalTtc;
      vatAmount = 0;

      taxCategory = "E";

      taxExemptionCode = "VATEX-FR-FRANCHISE";

      taxExemptionReason =
        "TVA non applicable, art. 293 B du CGI";
    }

    // Vendeur soumis à TVA
    else {
      if (vatRate < 0) {
        throw new Error("Taux TVA vendeur invalide");
      }

      if (vatRate > 0) {
        totalHt =
          totalTtc / (1 + vatRate / 100);

        vatAmount =
          totalTtc - totalHt;

        taxCategory = "S";
      } else {
        totalHt = totalTtc;
        vatAmount = 0;

        taxCategory = "Z";
      }
    }

    totalHt = Number(totalHt.toFixed(2));
    vatAmount = Number(vatAmount.toFixed(2));

    const finalTtc = Number(
      totalTtc.toFixed(2)
    );

    // =========================
    // 5. DATE
    // =========================
    const paidAt =
      paymentFields["Paid At"] || "";

    const invoiceDate = paidAt
      ? String(paidAt).slice(0, 10)
      : new Date().toISOString().slice(0, 10);

    // =========================
    // 6. OBJET NORMALISÉ NOVAPULSE
    // =========================
    const invoiceData = {
      invoice_type: "normal",

      invoice_number:
        paymentFields["Invoice Number"] || "",

      invoice_date: invoiceDate,

      payment_date: paidAt,

      currency: "EUR",

      // =====================
      // VENDEUR
      // =====================
      seller: {
        seller_slug: sellerSlug,

        name: company.name || "",
        legal_name: company.legal_name || "",
        legal_status: company.legal_status || "",

        siren: company.siren || "",
        siret: company.siret || "",

        address: company.address || "",
        postal_code: company.postal_code || "",
        city: company.city || "",
        country: company.country || "FR",

        email: company.email || "",
        phone: company.phone || "",

        vat_status: vatStatus,
        vat_number: company.vat_number || "",
        default_vat_rate: vatRate,

        logo: company.logo || ""
      },

      // =====================
      // ACHETEUR
      // =====================
      buyer: {
        type:
          paymentFields["Buyer Type"] || "",

        name:
          paymentFields["Buyer Name"] || "",

        company_name:
          paymentFields["Buyer Company Name"] || "",

        email:
          paymentFields["Buyer Email"] || "",

        phone:
          paymentFields["Buyer Phone"] || "",

        address_1:
          paymentFields["Buyer Address Line 1"] || "",

        address_2:
          paymentFields["Buyer Address Line 2"] || "",

        postal_code:
          paymentFields["Buyer Postal Code"] || "",

        city:
          paymentFields["Buyer City"] || "",

        country:
          paymentFields["Buyer Country"] || "",

        siret:
          paymentFields["Buyer SIRET"] || "",

        vat_number:
          paymentFields["Buyer VAT"] || ""
      },

      // =====================
      // LIGNE DE FACTURE
      // =====================
      lines: [
        {
          line_number: 1,

          description:
            paymentFields["Caption"] ||
            "Prestation",

          quantity: 1,

          unit: "C62",

          unit_price_ht: totalHt,

          line_total_ht: totalHt,

          vat_rate: vatRate,

          tax_category: taxCategory
        }
      ],

      // =====================
      // TVA
      // =====================
      tax: {
        status: vatStatus,

        category: taxCategory,

        rate: vatRate,

        taxable_amount: totalHt,

        tax_amount: vatAmount,

        exemption_code: taxExemptionCode,

        exemption_reason: taxExemptionReason
      },

      // =====================
      // TOTAUX
      // =====================
      totals: {
        total_ht: totalHt,

        vat_amount: vatAmount,

        total_ttc: finalTtc,

        prepaid_amount: finalTtc,

        payable_amount: 0
      },

      // =====================
      // TRAÇABILITÉ NOVAPULSE
      // =====================
      source: {
        payment_intent_id:
          paymentFields["Stripe Payment Intent ID"] || "",

        checkout_session_id:
          paymentFields["Checkout Session ID"] || "",

        quote_id: "",

        payment_role: ""
      }
    };

    console.log(
      "🧾 NORMAL INVOICE DATA BUILT |",
      invoiceData.invoice_number,
      "| seller:",
      sellerSlug,
      "| HT:",
      totalHt,
      "| TVA:",
      vatAmount,
      "| TTC:",
      finalTtc,
      "| tax:",
      taxCategory
    );

    return invoiceData;

  } catch (err) {
    console.error(
      "❌ buildNormalInvoiceData error:",
      err.message
    );

    return null;
  }
}

async function buildDepositInvoiceData(paymentFields, sellerSlug) {
  try {
    // =========================
    // 1. VÉRIFIER LE LIEN DEVIS
    // =========================
    const quoteId = String(
      paymentFields["Quote ID"] || ""
    ).trim();

    const paymentRole = String(
      paymentFields["Payment Role"] || ""
    ).trim();

    if (!quoteId || paymentRole !== "deposit") {
      throw new Error(
        "buildDepositInvoiceData appelé sur un paiement qui n'est pas un acompte de devis"
      );
    }

    // =========================
    // 2. CHARGER LE VENDEUR
    // =========================
    const sellerConfig = await getSellerConfig(sellerSlug);

    if (!sellerConfig?.company) {
      throw new Error(
        `Configuration vendeur introuvable : ${sellerSlug}`
      );
    }

    const company = sellerConfig.company;

    // =========================
    // 3. CHARGER LE DEVIS
    // =========================
    const quoteRecords = await base("Quotes")
      .select({
        filterByFormula: `{quote_id}='${quoteId}'`,
        maxRecords: 1
      })
      .firstPage();

    if (!quoteRecords.length) {
      throw new Error(
        `Devis introuvable : ${quoteId}`
      );
    }

    const quoteFields = quoteRecords[0].fields;

    // =========================
    // 4. DONNÉES FIGÉES DU DEVIS
    // =========================
    const totalHt = Number(
      String(quoteFields["total_ht"] || 0).replace(",", ".")
    );

    const vatRate = Number(
      String(quoteFields["tva_percent"] || 0).replace(",", ".")
    );

    const totalTtc = Number(
      String(quoteFields["total_ttc"] || 0).replace(",", ".")
    );

    const depositPercent = Number(
      String(quoteFields["deposit_percent"] || 0).replace(",", ".")
    );

    const depositTtc = Number(
      String(quoteFields["deposit_amount"] || 0).replace(",", ".")
    );

    if (!Number.isFinite(depositTtc) || depositTtc <= 0) {
      throw new Error("Montant acompte invalide");
    }

    // =========================
    // 5. CALCUL HT / TVA DE L'ACOMPTE
    // =========================
    let depositHt = depositTtc;
    let depositVat = 0;

    let taxCategory;
    let taxExemptionCode = "";
    let taxExemptionReason = "";

    if (vatRate > 0) {
      depositHt =
        depositTtc / (1 + vatRate / 100);

      depositVat =
        depositTtc - depositHt;

      taxCategory = "S";
    } else {
      depositHt = depositTtc;
      depositVat = 0;

      if (String(company.vat_status || "") === "franchise_base") {
        taxCategory = "E";
        taxExemptionCode = "VATEX-FR-FRANCHISE";
        taxExemptionReason =
          "TVA non applicable, art. 293 B du CGI";
      } else {
        taxCategory = "Z";
      }
    }

    depositHt = Number(depositHt.toFixed(2));
    depositVat = Number(depositVat.toFixed(2));

    const finalDepositTtc = Number(
      depositTtc.toFixed(2)
    );

    // =========================
    // 6. DATE
    // =========================
    const paidAt =
      paymentFields["Paid At"] || "";

    const invoiceDate = paidAt
      ? String(paidAt).slice(0, 10)
      : new Date().toISOString().slice(0, 10);

    // =========================
    // 7. OBJET NORMALISÉ
    // =========================
    const invoiceData = {
      invoice_type: "deposit",

      invoice_number:
        paymentFields["Invoice Number"] || "",

      invoice_date: invoiceDate,

      payment_date: paidAt,

      currency: "EUR",

      seller: {
        seller_slug: sellerSlug,

        name: company.name || "",
        legal_name: company.legal_name || "",
        legal_status: company.legal_status || "",

        siren: company.siren || "",
        siret: company.siret || "",

        address: company.address || "",
        postal_code: company.postal_code || "",
        city: company.city || "",
        country: company.country || "FR",

        email: company.email || "",
        phone: company.phone || "",

        vat_status: company.vat_status || "",
        vat_number: company.vat_number || "",
        default_vat_rate: company.default_vat_rate || 0
      },

      buyer: {
        type:
          paymentFields["Buyer Type"] || "",

        name:
          paymentFields["Buyer Name"] || "",

        company_name:
          paymentFields["Buyer Company Name"] || "",

        email:
          paymentFields["Buyer Email"] || "",

        phone:
          paymentFields["Buyer Phone"] || "",

        address_1:
          paymentFields["Buyer Address Line 1"] || "",

        address_2:
          paymentFields["Buyer Address Line 2"] || "",

        postal_code:
          paymentFields["Buyer Postal Code"] || "",

        city:
          paymentFields["Buyer City"] || "",

        country:
          paymentFields["Buyer Country"] || "",

        siret:
          paymentFields["Buyer SIRET"] || "",

        vat_number:
          paymentFields["Buyer VAT"] || ""
      },

      quote: {
        quote_id: quoteId,

        total_ht: totalHt,

        vat_rate: vatRate,

        total_ttc: totalTtc,

        deposit_percent: depositPercent,

        deposit_ttc: finalDepositTtc
      },

      lines: [
        {
          line_number: 1,

          description:
            `Acompte ${depositPercent}% - ${quoteId}`,

          quantity: 1,

          unit: "C62",

          unit_price_ht: depositHt,

          line_total_ht: depositHt,

          vat_rate: vatRate,

          tax_category: taxCategory
        }
      ],

      tax: {
        category: taxCategory,

        rate: vatRate,

        taxable_amount: depositHt,

        tax_amount: depositVat,

        exemption_code: taxExemptionCode,

        exemption_reason: taxExemptionReason
      },

      totals: {
        total_ht: depositHt,

        vat_amount: depositVat,

        total_ttc: finalDepositTtc,

        prepaid_amount: finalDepositTtc,

        payable_amount: 0
      },

      source: {
        payment_intent_id:
          paymentFields["Stripe Payment Intent ID"] || "",

        checkout_session_id:
          paymentFields["Checkout Session ID"] || "",

        quote_id: quoteId,

        payment_role: "deposit"
      }
    };

    console.log(
      "🧾 DEPOSIT INVOICE DATA BUILT |",
      invoiceData.invoice_number,
      "| quote:",
      quoteId,
      "| HT:",
      depositHt,
      "| TVA:",
      depositVat,
      "| TTC:",
      finalDepositTtc
    );

    return invoiceData;

  } catch (err) {
    console.error(
      "❌ buildDepositInvoiceData error:",
      err.message
    );

    return null;
  }
}

async function findPaidDepositForQuote(quoteId) {
  try {
    const cleanQuoteId = String(quoteId || "").trim();

    if (!cleanQuoteId) {
      throw new Error("Quote ID manquant");
    }

    const records = await base("Payment Links")
      .select({
        filterByFormula: `AND(
          {Quote ID}='${cleanQuoteId}',
          {Payment Role}='deposit',
          {Status}='Paid'
        )`,
        maxRecords: 1
      })
      .firstPage();

    if (!records.length) {
      console.log(
        "⚠️ Aucun acompte payé trouvé pour:",
        cleanQuoteId
      );

      return null;
    }

    const fields = records[0].fields;

    const depositData = {
      record_id: records[0].id,

      quote_id:
        fields["Quote ID"] || "",

      invoice_number:
        fields["Invoice Number"] || "",

      paid_at:
        fields["Paid At"] || "",

      amount_cents:
        Number(fields["Amount Cents"] || 0),

      amount:
        Number(fields["Amount Cents"] || 0) / 100,

      payment_intent_id:
        fields["Stripe Payment Intent ID"] || "",

      status:
        fields["Status"] || "",

      // =====================
      // ACHETEUR DE L'ACOMPTE
      // =====================
      buyer: {
        type:
          fields["Buyer Type"] || "",

        name:
          fields["Buyer Name"] || "",

        company_name:
          fields["Buyer Company Name"] || "",

        email:
          fields["Buyer Email"] || "",

        phone:
          fields["Buyer Phone"] || "",

        address_1:
          fields["Buyer Address Line 1"] || "",

        address_2:
          fields["Buyer Address Line 2"] || "",

        postal_code:
          fields["Buyer Postal Code"] || "",

        city:
          fields["Buyer City"] || "",

        country:
          fields["Buyer Country"] || "",

        siret:
          fields["Buyer SIRET"] || "",

        vat_number:
          fields["Buyer VAT"] || ""
      }
    };

    console.log(
      "🔎 PAID DEPOSIT FOUND |",
      depositData.quote_id,
      "| invoice:",
      depositData.invoice_number,
      "| amount:",
      depositData.amount
    );

    return depositData;

  } catch (err) {
    console.error(
      "❌ findPaidDepositForQuote error:",
      err.message
    );

    return null;
  }
}

async function buildBalanceInvoiceData(paymentFields, sellerSlug) {
  try {
    // =========================
    // 1. VÉRIFIER LE PAIEMENT
    // =========================
    const quoteId = String(
      paymentFields["Quote ID"] || ""
    ).trim();

    const paymentRole = String(
      paymentFields["Payment Role"] || ""
    ).trim();

    if (!quoteId || paymentRole !== "balance") {
      throw new Error(
        "buildBalanceInvoiceData appelé sur un paiement qui n'est pas un solde de devis"
      );
    }

    // =========================
    // 2. CHARGER LE VENDEUR
    // =========================
    const sellerConfig = await getSellerConfig(sellerSlug);

    if (!sellerConfig?.company) {
      throw new Error(
        `Configuration vendeur introuvable : ${sellerSlug}`
      );
    }

    const company = sellerConfig.company;

    // =========================
    // 3. CHARGER LE DEVIS
    // =========================
    const quoteRecords = await base("Quotes")
      .select({
        filterByFormula: `{quote_id}='${quoteId}'`,
        maxRecords: 1
      })
      .firstPage();

    if (!quoteRecords.length) {
      throw new Error(`Devis introuvable : ${quoteId}`);
    }

    const quoteFields = quoteRecords[0].fields;

    // =========================
    // 4. RETROUVER L'ACOMPTE PAYÉ
    // =========================
    const deposit = await findPaidDepositForQuote(quoteId);

    if (!deposit) {
      throw new Error(
        `Aucun acompte payé trouvé pour ${quoteId}`
      );
    }

    if (!deposit.invoice_number) {
      throw new Error(
        `Numéro de facture acompte manquant pour ${quoteId}`
      );
    }

    // =========================
    // 5. DONNÉES FIGÉES DU DEVIS
    // =========================
    const quoteTotalHt = Number(
      String(quoteFields["total_ht"] || 0).replace(",", ".")
    );

    const vatRate = Number(
      String(quoteFields["tva_percent"] || 0).replace(",", ".")
    );

    const quoteTotalTtc = Number(
      String(quoteFields["total_ttc"] || 0).replace(",", ".")
    );

    const depositTtc = Number(
      String(quoteFields["deposit_amount"] || 0).replace(",", ".")
    );

    const remainingTtc = Number(
      String(quoteFields["remaining_amount"] || 0).replace(",", ".")
    );

    if (
      !Number.isFinite(remainingTtc) ||
      remainingTtc <= 0
    ) {
      throw new Error("Montant du solde invalide");
    }

    // =========================
    // 6. CALCUL HT / TVA DU SOLDE
    // =========================
    let remainingHt = remainingTtc;
    let remainingVat = 0;

    let taxCategory;
    let taxExemptionCode = "";
    let taxExemptionReason = "";

    if (vatRate > 0) {
      remainingHt =
        remainingTtc / (1 + vatRate / 100);

      remainingVat =
        remainingTtc - remainingHt;

      taxCategory = "S";
    } else {
      remainingHt = remainingTtc;
      remainingVat = 0;

      if (
        String(company.vat_status || "") ===
        "franchise_base"
      ) {
        taxCategory = "E";

        taxExemptionCode =
          "VATEX-FR-FRANCHISE";

        taxExemptionReason =
          "TVA non applicable, art. 293 B du CGI";
      } else {
        taxCategory = "Z";
      }
    }

    remainingHt = Number(
      remainingHt.toFixed(2)
    );

    remainingVat = Number(
      remainingVat.toFixed(2)
    );

    const finalRemainingTtc = Number(
      remainingTtc.toFixed(2)
    );

    // =========================
    // 7. VÉRIFIER LE MONTANT STRIPE
    // =========================
    const paidAmount = Number(
      paymentFields["Amount Cents"] || 0
    ) / 100;

    if (
      Number(paidAmount.toFixed(2)) !==
      finalRemainingTtc
    ) {
      throw new Error(
        `Montant Stripe (${paidAmount}) différent du solde du devis (${finalRemainingTtc})`
      );
    }

    // =========================
    // 8. DATE
    // =========================
    const paidAt =
      paymentFields["Paid At"] || "";

    const invoiceDate = paidAt
      ? String(paidAt).slice(0, 10)
      : new Date().toISOString().slice(0, 10);

    // =========================
    // 9. OBJET NORMALISÉ
    // =========================
    const invoiceData = {
      invoice_type: "balance",

      invoice_number:
        paymentFields["Invoice Number"] || "",

      invoice_date: invoiceDate,

      payment_date: paidAt,

      currency: "EUR",

      // =====================
      // VENDEUR
      // =====================
      seller: {
        seller_slug: sellerSlug,

        name: company.name || "",
        legal_name: company.legal_name || "",
        legal_status: company.legal_status || "",

        siren: company.siren || "",
        siret: company.siret || "",

        address: company.address || "",
        postal_code: company.postal_code || "",
        city: company.city || "",
        country: company.country || "FR",

        email: company.email || "",
        phone: company.phone || "",

        vat_status: company.vat_status || "",
        vat_number: company.vat_number || "",
        default_vat_rate:
          company.default_vat_rate || 0
      },

      // =====================
      // ACHETEUR
      // =====================
      buyer: {
        type:
          paymentFields["Buyer Type"] ||
          deposit.buyer?.type ||
          "",

        name:
          paymentFields["Buyer Name"] ||
          deposit.buyer?.name ||
          "",

        company_name:
          paymentFields["Buyer Company Name"] ||
          deposit.buyer?.company_name ||
          "",

        email:
          paymentFields["Buyer Email"] ||
          deposit.buyer?.email ||
          "",

        phone:
          paymentFields["Buyer Phone"] ||
          deposit.buyer?.phone ||
          "",

        address_1:
          paymentFields["Buyer Address Line 1"] ||
          deposit.buyer?.address_1 ||
          "",

        address_2:
          paymentFields["Buyer Address Line 2"] ||
          deposit.buyer?.address_2 ||
          "",

        postal_code:
          paymentFields["Buyer Postal Code"] ||
          deposit.buyer?.postal_code ||
          "",

        city:
          paymentFields["Buyer City"] ||
          deposit.buyer?.city ||
          "",

        country:
          paymentFields["Buyer Country"] ||
          deposit.buyer?.country ||
          "",

        siret:
          paymentFields["Buyer SIRET"] ||
          deposit.buyer?.siret ||
          "",

        vat_number:
          paymentFields["Buyer VAT"] ||
          deposit.buyer?.vat_number ||
          ""
      },

      // =====================
      // DEVIS
      // =====================
      quote: {
        quote_id: quoteId,

        total_ht: quoteTotalHt,

        vat_rate: vatRate,

        total_ttc: quoteTotalTtc,

        deposit_ttc: Number(
          depositTtc.toFixed(2)
        ),

        remaining_ttc:
          finalRemainingTtc
      },

      // =====================
      // FACTURE D'ACOMPTE LIÉE
      // =====================
      deposit_reference: {
        invoice_number:
          deposit.invoice_number,

        invoice_date:
          deposit.paid_at
            ? String(deposit.paid_at).slice(0, 10)
            : "",

        amount:
          Number(deposit.amount.toFixed(2)),

        payment_intent_id:
          deposit.payment_intent_id || ""
      },

      // =====================
      // LIGNE FACTURE
      // =====================
      lines: [
        {
          line_number: 1,

          description:
            `Solde devis ${quoteId}`,

          quantity: 1,

          unit: "C62",

          unit_price_ht: remainingHt,

          line_total_ht: remainingHt,

          vat_rate: vatRate,

          tax_category: taxCategory
        }
      ],

      // =====================
      // TVA
      // =====================
      tax: {
        category: taxCategory,

        rate: vatRate,

        taxable_amount: remainingHt,

        tax_amount: remainingVat,

        exemption_code:
          taxExemptionCode,

        exemption_reason:
          taxExemptionReason
      },

      // =====================
      // TOTAUX DU SOLDE
      // =====================
      totals: {
        total_ht: remainingHt,

        vat_amount: remainingVat,

        total_ttc: finalRemainingTtc,

        prepaid_amount:
          finalRemainingTtc,

        payable_amount: 0
      },

      // =====================
      // TRAÇABILITÉ
      // =====================
      source: {
        payment_intent_id:
          paymentFields["Stripe Payment Intent ID"] || "",

        checkout_session_id:
          paymentFields["Checkout Session ID"] || "",

        quote_id: quoteId,

        payment_role: "balance"
      }
    };

    console.log(
      "🧾 BALANCE INVOICE DATA BUILT |",
      invoiceData.invoice_number,
      "| quote:",
      quoteId,
      "| deposit invoice:",
      deposit.invoice_number,
      "| HT:",
      remainingHt,
      "| TVA:",
      remainingVat,
      "| TTC:",
      finalRemainingTtc
    );

    return invoiceData;

  } catch (err) {
    console.error(
      "❌ buildBalanceInvoiceData error:",
      err.message
    );

    return null;
  }
}
return { buildNormalInvoiceData, buildDepositInvoiceData, buildBalanceInvoiceData, findPaidDepositForQuote };
}
module.exports = { createInvoiceBuilders };
