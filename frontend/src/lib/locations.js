export function locationName(location) {
  return location ? `${location.building} · ${location.room_or_area}` : "Location unavailable";
}
