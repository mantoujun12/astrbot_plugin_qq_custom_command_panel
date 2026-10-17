import { describe, expect, it } from 'vitest'
import { vuetify } from '../plugins/vuetify'
import {
  DEFAULT_THEME_COLORS,
  THEME_DARK,
  THEME_LIGHT,
  applyThemeColors,
  darkTheme,
  lightTheme,
  resolveThemeColors,
} from './index'

const SHARED_COLOR_KEYS = [
  'primary',
  'secondary',
  'info',
  'success',
  'warning',
  'error',
  'background',
  'surface',
  'borderLight',
  'primaryText',
  'secondaryText',
]

describe('theme palette', () => {
  it('uses distinct theme names', () => {
    expect(THEME_LIGHT).not.toBe(THEME_DARK)
  })

  it('marks the palettes as light and dark', () => {
    expect(lightTheme.dark).toBe(false)
    expect(darkTheme.dark).toBe(true)
  })

  it('defines the same color keys in both palettes', () => {
    expect(Object.keys(darkTheme.colors ?? {}).sort()).toEqual(
      Object.keys(lightTheme.colors ?? {}).sort(),
    )
  })

  it('covers every color key the views rely on', () => {
    for (const key of SHARED_COLOR_KEYS) {
      expect(lightTheme.colors).toHaveProperty(key)
      expect(darkTheme.colors).toHaveProperty(key)
    }
  })

  it('resolves saved colors and falls back for invalid values', () => {
    expect(
      resolveThemeColors({
        primary_color: '#AABBCC',
        secondary_color: 'not-a-color',
      }),
    ).toEqual({
      primary: '#aabbcc',
      secondary: DEFAULT_THEME_COLORS.secondary,
    })
  })

  it('applies configured colors to both registered themes', () => {
    try {
      applyThemeColors(vuetify.theme, {
        primary: '#112233',
        secondary: '#445566',
      })

      expect(vuetify.theme.themes.value[THEME_LIGHT]?.colors.primary).toBe('#112233')
      expect(vuetify.theme.themes.value[THEME_LIGHT]?.colors.secondary).toBe('#445566')
      expect(vuetify.theme.themes.value[THEME_DARK]?.colors.primary).toBe('#112233')
      expect(vuetify.theme.themes.value[THEME_DARK]?.colors.secondary).toBe('#445566')
    } finally {
      applyThemeColors(vuetify.theme, DEFAULT_THEME_COLORS)
    }
  })
})
