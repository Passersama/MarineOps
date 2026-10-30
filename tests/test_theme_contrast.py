"""Contrast checks for readable text and key control boundaries."""
import unittest

from cargo_track.theme_tokens import DARK, LIGHT


def contrast(first, second):
    def luminance(color):
        values = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        values = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in values]
        return sum(value * weight for value, weight in zip(values, (.2126, .7152, .0722)))
    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (lighter + .05) / (darker + .05)


class ThemeContrastTests(unittest.TestCase):
    def test_text_and_statuses(self):
        for theme in (LIGHT, DARK):
            for foreground, background in (('text', 'surface'), ('muted', 'surface'),
                    ('primary_text', 'primary'), ('waiting_text', 'waiting_surface'),
                    ('onboard_text', 'onboard_surface'), ('done_text', 'done_surface')):
                with self.subTest(foreground=foreground, background=background, theme=theme['window']):
                    self.assertGreaterEqual(contrast(theme[foreground], theme[background]), 4.5)

    def test_input_boundary_against_surface(self):
        for theme in (LIGHT, DARK):
            self.assertGreaterEqual(contrast(theme['border'], theme['surface']), 3.0)
