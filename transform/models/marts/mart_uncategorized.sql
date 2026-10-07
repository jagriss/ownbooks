-- The categorization to-do list: descriptions no merchant rule covers,
-- biggest money first. Includes ones categorized only by the bank's
-- own category (category_source = 'bank'), with that guess shown, so
-- they can be confirmed or corrected by writing a rule.

SELECT
    clean_description,
    count(*) AS txn_count,
    sum(amount) AS total_amount,
    min(txn_date) AS first_seen,
    max(txn_date) AS last_seen,
    -- The bank-derived guess, if any of its transactions have one.
    mode(category) FILTER (WHERE category_source = 'bank') AS bank_guess,
    count(*) FILTER (WHERE category_source = 'none') AS uncategorized_count,
    string_agg(DISTINCT account_key, ', ') AS account_keys,
    any_value(raw_description) AS example_raw_description
FROM {{ ref('fct_transactions') }}
WHERE category_source != 'rule'
GROUP BY clean_description
ORDER BY abs(sum(amount)) DESC
