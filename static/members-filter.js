// RO-4: submit the roster's filter form as soon as a dropdown changes, so the page needs no
// Apply button (awkward to find on a phone). Without JavaScript the form's own <noscript> button does it.
document.querySelectorAll("#member-filters select").forEach((select) => {
  select.addEventListener("change", () => select.form.submit());
});
