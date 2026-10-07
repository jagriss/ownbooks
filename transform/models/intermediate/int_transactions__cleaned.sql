-- Reduces bank descriptions to a form merchant rules can match
-- reliably: one case, single spaces, no point-of-sale processor
-- prefixes, and no ACH trace IDs or store/terminal numbers.

WITH unioned AS (
    SELECT
        txn_id
        ,account_key
        ,institution
        ,txn_date
        ,description
        ,raw_description
        ,amount
        ,bank_type
        ,bank_category
        ,source_file
        ,extracted_at
    FROM {{ ref('int_transactions__unioned') }}
)

,normalized AS (
    SELECT
        txn_id
        ,account_key
        ,institution
        ,txn_date
        ,description
        ,raw_description
        ,amount
        ,bank_type
        ,bank_category
        ,source_file
        ,extracted_at
        ,regexp_replace(upper(trim(description)), '\s+', ' ', 'g')
            AS normalized_description
    FROM unioned
)

,prefixes_stripped AS (
    SELECT
        txn_id
        ,account_key
        ,institution
        ,txn_date
        ,description
        ,raw_description
        ,amount
        ,bank_type
        ,bank_category
        ,source_file
        ,extracted_at
        -- Square, Toast, Shopify, PayPal, and DoorDash processor prefixes.
        ,regexp_replace(
            normalized_description
            ,'^(SQ \*|TST\* ?|SP \* ?|PAYPAL \*|PP\*|DD \*)'
            ,''
        ) AS no_prefix_description
    FROM normalized
)

,cleaned AS (
    SELECT
        txn_id
        ,account_key
        ,institution
        ,txn_date
        ,description
        ,raw_description
        ,amount
        ,bank_type
        ,bank_category
        ,source_file
        ,extracted_at
        ,trim(
            regexp_replace(
                regexp_replace(
                    no_prefix_description
                    -- ACH trace IDs and Zelle confirmation codes.
                    ,'\s+(PPD ID:|WEB ID:|CCD ID:|JPM[0-9A-Z]+).*$'
                    ,''
                )
                -- The first store/terminal/reference number onward, e.g.
                -- "WHOLEFDS MKT 10234" or "ACH PMT M5501".
                ,'\s+#?[A-Z]*\d{3,}.*$'
                ,''
            )
        ) AS clean_description
    FROM prefixes_stripped
)

,final AS (
    SELECT
        txn_id
        ,account_key
        ,institution
        ,txn_date
        ,description
        ,raw_description
        ,amount
        ,bank_type
        ,bank_category
        ,source_file
        ,extracted_at
        ,clean_description
    FROM cleaned
)

SELECT
*
FROM final
