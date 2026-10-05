"""Additional tests; the supplied lab tests and benchmark are unchanged."""

import json
import unicodedata

import pytest

from src.graph import Document, extract_news_cases, load_markdown_docs, parse_law_article
from src.graph_rules import (bounded_facts, canonical_substance, find_substances, link_entity,
                             matching_threshold, parse_amount)


@pytest.mark.parametrize('mention,expected', [
    ('sử dụng trái phép chất ma túy', None),
    ('sử dụng ma túy', None),
    ('mua bán ma túy', 'mua bán trái phép chất ma túy'),
    ('vận chuyển ma túy', 'vận chuyển trái phép chất ma túy'),
    ('Tội vận chuyển trái phép chất ma tuý', 'vận chuyển trái phép chất ma túy'),
])
def test_link_preserves_action(mention, expected):
    known = ['mua bán trái phép chất ma túy', 'vận chuyển trái phép chất ma túy',
             'tổ chức sử dụng trái phép chất ma túy']
    assert link_entity(mention, known) == expected


def test_unicode_normalization():
    known = ['mua bán trái phép chất ma túy']
    assert link_entity(unicodedata.normalize('NFD', known[0]), known) == known[0]


@pytest.mark.parametrize('mention', ['ma túy tổng hợp', 'thuốc lắc và Ketamine', 'đá', 'cỏ'])
def test_ambiguous_substances_are_preserved(mention):
    assert canonical_substance(mention) == mention


def test_substances_respect_word_boundaries():
    assert find_substances('Methamphetamine') == ['Methamphetamine']
    assert find_substances('MDMA và thuốc lắc, Ketamine') == ['MDMA', 'Ketamine']


@pytest.mark.parametrize('amount,g,qualifier', [
    ('hơn 9,6kg', 9600, 'gt'), ('100 gam', 100, 'eq'),
    ('gần 406g', 406, 'approx'), ('5 viên', None, 'unknown'),
    ('5-10g', None, 'unknown'), ('5g; 10g', None, 'unknown'),
])
def test_mass_keeps_uncertainty(amount, g, qualifier):
    assert parse_amount(amount) == {'grams': g, 'qualifier': qualifier}


def test_mdma_clause_boundary_and_open_lower_bound():
    doc = next(d for d in load_markdown_docs('data/drug_law') if d.id == 'blhs-dieu-250')
    clauses = parse_law_article(doc)['clauses']
    for amount, expected in [('99,999g', [3]), ('100g', [4]), ('hơn 9,6kg', [4]),
                             ('hơn 5g', []), ('khoảng 100g', [])]:
        matched = [r['number'] for r in clauses if matching_threshold(r, {'name':'MDMA', 'amount':amount})]
        assert matched == expected


def test_budget_does_not_cut_conditions_or_duplicates():
    facts = ['short', 'a very long legal condition', 'short', 'ok']
    assert bounded_facts(facts, max_facts=3, max_chars=8) == ['short', 'ok']


def test_extraction_rejects_invalid_json_instead_of_silent_loss():
    doc = Document('news-test', 'body', {})
    with pytest.raises(ValueError, match='news-test'):
        extract_news_cases(doc, lambda _: '{broken', [])


def test_extraction_preserves_conflicting_masses_and_explicit_alias():
    doc = Document('news-test', 'Dương Minh Tuấn (43 tuổi, tức "Hoàng Nato")', {})
    payload = {'cases':[{'name':'same name', 'people':[{'name':'Dương Minh Tuấn'}],
                        'substances':[{'name':'MDMA','amount':'5g'}, {'name':'thuốc lắc','amount':'10g'}]}]}
    case = extract_news_cases(doc, lambda _: json.dumps(payload), [])[0]
    assert case['substances'][0]['amount_g'] is None
    assert case['substances'][0]['amount'] == '5g; 10g'
    assert 'hoàng nato' in case['people'][0]['aliases']
    other = extract_news_cases(Document('other', doc.content, {}), lambda _: json.dumps(payload), [])[0]
    assert other['id'] != case['id']
