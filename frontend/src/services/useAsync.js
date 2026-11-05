import { useEffect, useState } from 'react';

// Runs load() whenever deps change and ignores responses from earlier runs.
export function useAsync(load, deps) {
  const [state, setState] = useState({ loading: true, data: null, error: null });

  useEffect(() => {
    let current = true;
    setState({ loading: true, data: null, error: null });
    load()
      .then((data) => current && setState({ loading: false, data, error: null }))
      .catch((error) => current && setState({ loading: false, data: null, error: error.message }));
    return () => {
      current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}
