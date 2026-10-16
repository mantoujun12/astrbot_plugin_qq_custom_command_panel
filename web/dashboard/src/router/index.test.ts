import { describe, expect, it } from 'vitest'
import { router } from './index'

describe('router', () => {
  it('resolves the robot and compatibility views by path and by name', () => {
    expect(router.resolve('/robots').name).toBe('robots')
    expect(router.resolve({ name: 'robots' }).path).toBe('/robots')
    expect(router.resolve('/settings').name).toBe('settings')
    expect(router.resolve({ name: 'settings' }).path).toBe('/settings')
  })

  it('redirects the root path to the status view', async () => {
    await router.push('/')

    expect(router.currentRoute.value.name).toBe('status')
  })

  it('redirects unknown paths to the status view', async () => {
    await router.push('/not-a-view')

    expect(router.currentRoute.value.name).toBe('status')
  })

  it('keeps the location in the hash', async () => {
    await router.push('/settings')

    expect(router.currentRoute.value.name).toBe('settings')
    expect(window.location.hash).toBe('#/settings')
  })
})
