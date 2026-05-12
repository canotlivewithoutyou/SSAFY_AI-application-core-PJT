window.PLANNER_API_BASE =
  window.location.port === "8000"
    ? `${window.location.origin}/api/v1`
    : `${window.location.protocol}//${window.location.hostname}:8000/api/v1`;

