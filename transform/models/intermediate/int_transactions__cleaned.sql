-- Normalizes bank description noise down to something merchant rules
-- can match reliably: one case, single spaces, no point-of-sale
-- processor prefixes, no ACH trace IDs or store/terminal numbers.

WITH unioned AS (

    SELECT *
    FROM {{ ref('int_transactions__unioned') }}

),

normalized AS (

    SELECT
        *,
        regexp_replace(upper(trim(description)), '\s+', ' ', 'g')
            AS normalized_description
    FROM unioned

),

prefixes_stripped AS (

    SELECT
        *,
        -- Square, Toast, Shopify, PayPal, DoorDash processor prefixes.
        regexp_replace(
            normalized_description,
            '^(SQ \*|TST\* ?|SP \* ?|PAYPAL \*|PP\*|DD \*)',
            ''
        ) AS no_prefix_description
    FROM normalized

),

cleaned AS (

    SELECT
        *,
        trim(
            regexp_replace(
                regexp_replace(
                    no_prefix_description,
                    -- ACH trace IDs and Zelle confirmation codes.
                    '\s+(PPD ID:|WEB ID:|CCD ID:|JPM[0-9A-Z]+).*$',
                    ''
                ),
                -- First store/terminal/reference number onward, e.g.
                -- "WHOLEFDS MKT 10234" or "ACH PMT M5501".
                '\s+#?[A-Z]*\d{3,}.*$',
                ''
            )
        ) AS clean_description
    FROM prefixes_stripped

)

SELECT * EXCLUDE (normalized_description, no_prefix_description)
FROM cleaned
