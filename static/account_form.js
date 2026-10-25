// AC-5: show the section boxes for a section leader, and "Admins see all sections" for an admin, as the
// role changes. Only a convenience: the server ignores submitted sections for an admin and requires them
// for a leader whatever this script did, so the form is still correct without JavaScript.
const role = document.querySelector("#account-form select[name='role']");
const boxes = document.getElementById("section-boxes");
const note = document.getElementById("admin-note");

function update() {
  const isAdmin = role.value === "admin";
  boxes.hidden = isAdmin;
  note.hidden = !isAdmin;
}

role.addEventListener("change", update);
update();
