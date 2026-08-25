/* Global admin search + misc UI helpers */
function globalSearch() {
  return {
    q: '',
    results: [],
    doSearch() {
      if (this.q.length < 2) { this.results = []; return; }
      fetch('/api/v1/search?q=' + encodeURIComponent(this.q))
        .then(r => r.json())
        .then(d => {
          this.results = [
            ...(d.patients || []).map(p => ({
              type: 'patient', label: p.code + ' — ' + p.name + ' (' + p.mobile + ')',
              url: '/admin/patients/' + p.id
            })),
            ...(d.invoices || []).map(i => ({
              type: 'invoice', label: i.code + ' — ' + i.patient + ' ₹' + i.grand_total,
              url: '/admin/invoices/' + i.id
            })),
            ...(d.bookings || []).map(b => ({
              type: 'booking', label: b.code + ' — ' + b.name + ' ' + b.status_label,
              url: '/admin/bookings/' + b.id
            }))
          ].slice(0, 10);
        });
    }
  };
}
