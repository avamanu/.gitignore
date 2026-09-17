import pytest

from pr_agent import pitch

CLEAN = "Hi Jane, your episode on sleep and shift work was careful about the evidence, which is rare. I research head injury and neurodegeneration at King's, and I run public sessions on brain health. Would a short call be useful?"


def test_clean_email_passes():
    assert pitch.lint("Sleep, shift work and the brain", CLEAN, 170) == []


def test_catches_dashes_banned_phrases_and_us_spellings():
    issues = pitch.lint("A game-changer", "Moreover, I hope this email finds you well — our behavior program is cutting-edge.", 170)
    joined = " ".join(issues)
    assert "em or en dash" in joined
    assert "moreover" in joined
    assert "game-changer" in joined
    assert "behavior" in joined


def test_catches_binary_contrast():
    assert any("binary contrast" in i for i in
               pitch.lint("Subject", "This is not just about sleep, but about recovery.", 170))


def test_catches_length_and_placeholders():
    long_body = "word " * 200
    issues = pitch.lint("S", long_body + "[insert name]", 170)
    assert any("words (limit 170)" in i for i in issues)
    assert any("placeholder" in i for i in issues)


def test_subject_length_is_checked_for_pitches_but_not_follow_ups():
    subject = "Re: " + "a specific and quite long subject line about brain health"
    assert any("characters (limit 60)" in i for i in pitch.lint(subject, CLEAN, 170))
    assert pitch.lint(subject, CLEAN, 170, check_subject=False) == []


def test_footer_carries_the_signature_and_opt_out():
    from pr_agent.config import SETTINGS
    footer = pitch.footer()
    assert SETTINGS["sign_off"] in footer
    assert SETTINGS["signature"].strip().splitlines()[0] in footer
    assert SETTINGS["opt_out_line"] in footer


CREDENTIAL_CLAIMS = [
    "I am a neurologist based in London.",
    "As a doctor, I see this pattern often.",
    "My patients ask about this constantly.",
    "Dr Vamanu would be glad to join the panel.",
    "I diagnose head injury most weeks.",
]


@pytest.mark.parametrize("claim", CREDENTIAL_CLAIMS)
def test_credentials_he_does_not_hold_are_caught(claim):
    assert any("false credential" in i for i in pitch.lint("Subject", claim, 170)), claim


def test_accurate_descriptions_are_left_alone():
    """The checks must not fire on what is actually true of him."""
    fine = [
        "I am a clinical neuroscientist and a PhD researcher at King's.",
        "I work alongside neurosurgeons and neurologists at the brain bank.",
        "I spend my week with post mortem brain tissue.",
        "A neurologist I work with raised the same question.",
    ]
    for sentence in fine:
        assert pitch.lint("Subject", sentence, 170) == [], sentence


def test_overclaiming_about_evidence_is_caught():
    for claim in ["Science proves that sleep matters.",
                  "This changes everything for dementia.",
                  "We can reverse ageing with one trick."]:
        assert pitch.lint("Subject", claim, 170), claim
