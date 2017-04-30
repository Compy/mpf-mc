from typing import List

from kivy.properties import NumericProperty, ListProperty

from mpfmc.effects.color_dmd import ColorDmdEffect
from mpfmc.effects.dot_filter import DotFilterEffect
from mpfmc.effects.monochrome import MonochromeEffect
from mpfmc.effects.reduce import ReduceEffect
from mpfmc.effects.colorize import ColorizeEffect
from mpfmc.effects.gain import GainEffect


class DmdEffect(ColorDmdEffect):

    """GLSL effect to render an on-screen DMD to look like individual round pixels."""

    luminosity = ListProperty([.299, .587, .114, 0])
    '''This defines the luminosity factor for each color channel. The value
    for each channel must be between 0.0 and 1.0.

    :attr:`luminosity` is a :class:`ListProperty` defaults to
    (.299, .587, .114, 0)
    '''

    shades = NumericProperty(16)
    '''
    Sets the number of shades per channel to reduce it to.

    shades is a :class:`~kivy.properties.NumericProperty` and
    defaults to 16.
    '''

    tint_color = ListProperty([1, 0.4, 0, 0])
    '''This defines the color tint to be used in the effect.

    :attr:`tint_color` is a :class:`ListProperty` defaults to
    (1, 0.4, 1, 0)
    '''

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_effects(self) -> List["EffectBase"]:
        effects = []

        if self.dot_filter:
            effects.append(DotFilterEffect(
                width=self.width,
                height=self.height,
                dots_x=self.dots_x,
                dots_y=self.dots_y,
                blur=self.blur,
                dot_size=self.dot_size,
                background_color=self.background_color
            ))

        effects.append(MonochromeEffect(luminosity=self.luminosity))
        effects.append(ReduceEffect(shades=self.shades))
        effects.append(ColorizeEffect(tint_color=self.tint_color))
        effects.append(GainEffect(gain=self.gain))

        return effects


effect_cls = DmdEffect
name = 'dmd'
