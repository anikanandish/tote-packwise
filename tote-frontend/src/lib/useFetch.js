import { useCallback, useEffect, useState } from 'react'
import { api } from './api'

// useFetch('/api/products') -> { data, error, loading, reload }
export default function useFetch(path, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const load = useCallback(() => {
    if (!path) return
    setState((s) => ({ ...s, loading: true, error: null }))
    api(path).then((data) => setState({ data, error: null, loading: false }))
      .catch((error) => setState({ data: null, error, loading: false }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps])
  useEffect(() => { load() }, [load])
  return { ...state, reload: load }
}
