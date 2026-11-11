// Demo fixtures for the supervisor dashboard. Dates are relative to the day the
// demo data is first created so upcoming and past examples stay meaningful.
import { addDays } from "../../lib/campusTime";

export const DEMO_SUPERVISOR = {
  user_id: "demo-supervisor",
  name: "Demo Supervisor",
  email: "supervisor@example.edu",
  role: "supervisor",
};

const PEER_EDUCATORS = [
  ["u01", "Maya Chen"],
  ["u02", "Jordan Lee"],
  ["u03", "Priya Patel"],
  ["u04", "Diego Ramirez"],
  ["u05", "Aisha Khan"],
  ["u06", "Ethan Nguyen"],
  ["u07", "Sofia Garcia"],
  ["u08", "Liam Johnson"],
  ["u09", "Hana Kim"],
  ["u10", "Noah Williams"],
];

const LOCATIONS = [
  {
    location_id: 1,
    building: "Martin Luther King Jr. Library",
    room_or_area: "Room 255",
    directions: "Take the elevators to the 2nd floor and turn left past the study rooms.",
    map_url: "https://www.google.com/maps/search/?api=1&query=King+Library+San+Jose",
  },
  {
    location_id: 2,
    building: "Student Union",
    room_or_area: "Ballroom A",
    directions: "Main entrance on the east side, then follow signs to the ballrooms.",
    map_url: "https://www.google.com/maps/search/?api=1&query=Student+Union+San+Jose+State",
  },
  {
    location_id: 3,
    building: "Clark Hall",
    room_or_area: "Room 118",
    directions: null,
    map_url: null,
  },
  {
    location_id: 4,
    building: "Engineering Building",
    room_or_area: "Room 189",
    directions: "Enter from the courtyard; the room is next to the student lounge.",
    map_url: null,
  },
  {
    location_id: 5,
    building: "Student Wellness Center",
    room_or_area: "Multipurpose Room",
    directions: null,
    map_url: "https://www.google.com/maps/search/?api=1&query=Student+Wellness+Center+San+Jose",
  },
];

// Each shift: [dayOffset, start, end, locationId, capacity, registrants].
// A registrant prefixed with "~" is a cancelled registration (kept as history).
const EVENT_PLANS = [
  {
    title: "Fall Peer Tutoring Kickoff",
    description: "Welcome table and drop-in tutoring to launch the semester. Fully staffed.",
    shifts: [
      [3, "10:00", "12:00", 1, 2, ["u01", "u02"]],
      [3, "13:00", "15:00", 1, 3, ["u03", "u04", "u05"]],
    ],
  },
  {
    title: "Midterm Study Jam",
    description: "Evening group study sessions with peer educators at every table.",
    shifts: [
      [7, "17:00", "19:00", 2, 4, ["u01", "u06", "~u05"]],
      [8, "17:00", "19:00", 2, 4, ["u07"]],
      [9, "17:00", "19:00", 2, 4, []],
    ],
  },
  {
    title: "Writing Center Drop-in Hours",
    description: "Help students outline and revise essays. No one has signed up yet.",
    shifts: [
      [10, "09:00", "11:00", 3, 2, []],
      [12, "09:00", "11:00", 3, 2, []],
    ],
  },
  {
    title: "Finals Week Math Support",
    description: "Extra coverage for calculus and statistics review before finals.",
    is_urgent: true,
    shifts: [
      [2, "18:00", "20:00", 4, 5, ["u02"]],
      [4, "18:00", "20:00", 4, 5, ["u08", "u09"]],
    ],
  },
  {
    title: "New Student Orientation Mentors",
    description: "Peer mentors guided new students through campus resources.",
    shifts: [
      [-21, "09:00", "12:00", 5, 4, ["u01", "u03", "u05", "u10"]],
      [-20, "09:00", "12:00", 5, 4, ["u02", "u04"]],
    ],
  },
  {
    title: "Career Fair Volunteer Desk",
    description: "Check-in desk support for the campus career fair.",
    status: "cancelled",
    shifts: [[5, "11:00", "14:00", 2, 3, ["u06", "u07"]]],
  },
  {
    title: "Study Skills Workshop Series",
    description: "A weekly workshop on note-taking and time management that runs for four weeks.",
    shifts: [
      [-3, "15:00", "16:30", 1, 3, ["u03", "u09"]],
      [4, "15:00", "16:30", 1, 3, ["u03"]],
      [11, "15:00", "16:30", 1, 3, []],
      [18, "15:00", "16:30", 1, 3, ["u10"]],
    ],
  },
  {
    title: "Spring Outreach Planning",
    description: "Draft planning session. Not published yet.",
    status: "draft",
    shifts: [[30, "14:00", "15:00", 3, 2, []]],
  },
  {
    // Overlaps Midterm Study Jam's first shift (17:00–19:00) and also has a
    // back-to-back shift, for testing schedule-conflict rules.
    title: "Peer Mentor Check-in",
    description: "Quick evening check-ins with new peer mentors after the first study jam.",
    shifts: [
      [7, "18:00", "19:30", 3, 3, ["u04"]],
      [7, "19:00", "20:00", 4, 2, []],
    ],
  },
];

export function createSeedData(today, nowIso = new Date().toISOString()) {
  const users = [
    DEMO_SUPERVISOR,
    ...PEER_EDUCATORS.map(([user_id, name]) => ({
      user_id,
      name,
      email: `${name.toLowerCase().replace(" ", ".")}@example.edu`,
      role: "peer_educator",
    })),
  ];

  const events = [];
  const shifts = [];
  const registrations = [];
  let shiftId = 1;
  let registrationId = 1;

  EVENT_PLANS.forEach((plan, index) => {
    const event_id = index + 1;
    events.push({
      event_id,
      title: plan.title,
      description: plan.description,
      is_urgent: Boolean(plan.is_urgent),
      status: plan.status ?? "published",
      organizer_id: DEMO_SUPERVISOR.user_id,
      created_at: nowIso,
      updated_at: nowIso,
      cancelled_at: plan.status === "cancelled" ? nowIso : null,
    });

    plan.shifts.forEach(([offset, start_time, end_time, location_id, capacity, registrants]) => {
      const shift_id = shiftId++;
      shifts.push({
        shift_id,
        event_id,
        shift_date: addDays(today, offset),
        start_time,
        end_time,
        location_id,
        capacity,
      });
      registrants.forEach((entry) => {
        const cancelled = entry.startsWith("~");
        registrations.push({
          registration_id: registrationId++,
          shift_id,
          user_id: cancelled ? entry.slice(1) : entry,
          status: cancelled ? "cancelled" : "active",
          created_at: nowIso,
          cancelled_at: cancelled ? nowIso : null,
        });
      });
    });
  });

  return { users, locations: LOCATIONS.map((location) => ({ ...location })), events, shifts, registrations };
}
