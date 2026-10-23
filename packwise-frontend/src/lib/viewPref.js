// Which carton view the worker prefers. Top view is the default: it is the layout the
// packing algorithm optimises (the floor), shown exactly to scale.
const KEY = 'packwise.view.v2'
export const readView = () => { try { return localStorage.getItem(KEY) || 'top' } catch { return 'top' } }
export const saveView = (v) => { try { localStorage.setItem(KEY, v) } catch { /* ignore */ } }
