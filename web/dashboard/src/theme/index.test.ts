import { describe, expect, it } from 'vitest'
import { THEME_DARK, THEME_LIGHT, darkTheme, lightTheme } from './index'

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
})
