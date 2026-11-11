import { useCallback, useEffect, useRef, useState } from "react";

// Runs an async fetcher whenever `key` changes (or reload() is called).
// Pass key = null to skip. `data` is only the result for the current key;
// `latestData` keeps the previous result visible while a new one loads.
export function useQuery(key, fetcher) {
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  const [reloadCount, setReloadCount] = useState(0);
  const [result, setResult] = useState(null);
  const requestKey = key === null ? null : `${key}#${reloadCount}`;

  useEffect(() => {
    if (requestKey === null) return undefined;
    let ignore = false;
    fetcherRef.current().then(
      (data) => {
        if (!ignore) setResult({ key: requestKey, data, error: null });
      },
      (error) => {
        if (!ignore) setResult({ key: requestKey, data: undefined, error });
      },
    );
    return () => {
      ignore = true;
    };
  }, [requestKey]);

  const current = result?.key === requestKey ? result : null;
  const reload = useCallback(() => setReloadCount((count) => count + 1), []);

  return {
    data: current?.data,
    latestData: current ? current.data : result?.data,
    error: current?.error ?? null,
    isLoading: requestKey !== null && !current,
    reload,
  };
}
