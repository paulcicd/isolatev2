(() => {
  const inventory = document.querySelector('.admin-inventory');
  if (!inventory) return;

  const selection = inventory.querySelector('.inventory-selection');
  const rowCheckbox = 'input[name="selected_host_id"]';
  function showSelection() {
    if (!selection) return;
    const count = inventory.querySelectorAll(rowCheckbox + ':checked').length;
    selection.querySelector('strong').textContent = count;
    selection.hidden = count === 0;
  }
  inventory.addEventListener('change', (event) => {
    if (event.target.matches(rowCheckbox)) showSelection();
  });
  showSelection();
})();
