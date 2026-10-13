/**
 * 主题调色板: 色值对齐 AstrBot 宿主 dashboard 的 LightTheme / DarkTheme,
 * 只保留本视图用得到的键。
 *
 * 插件视图跑在受限 iframe 里, 宿主的 --v-theme-* 不会继承进来, 必须自带一份。
 */

import type { ThemeDefinition } from 'vuetify'

/** 主题名会同时作为 DOM class: v-theme--<name> */
export const THEME_LIGHT = 'qcPanelTheme'
export const THEME_DARK = 'qcPanelThemeDark'

export const lightTheme: ThemeDefinition = {
  dark: false,
  colors: {
    primary: '#3c96ca',
    secondary: '#2f86bd',
    info: '#03c9d7',
    success: '#00c853',
    warning: '#ffc107',
    error: '#f44336',
    background: '#ffffff',
    surface: '#ffffff',
    borderLight: '#d0d0d0',
    primaryText: '#1b1c1d',
    secondaryText: '#000000aa',
  },
}

export const darkTheme: ThemeDefinition = {
  dark: true,
  colors: {
    primary: '#5ba4d4',
    secondary: '#4a95c4',
    info: '#03c9d7',
    success: '#52c41a',
    warning: '#faad14',
    error: '#ff4d4f',
    background: '#1a1a1a',
    surface: '#242424',
    borderLight: '#3a3a3a',
    primaryText: '#e8eaed',
    secondaryText: '#ffffffdd',
  },
}
