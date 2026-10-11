(() => {
  const tg = window.Telegram?.WebApp;
  tg?.ready(); tg?.expand();
  const draftId = new URLSearchParams(location.hash.slice(1)).get('draft');
  const form = document.getElementById('contactForm');
  const message = document.getElementById('message');
  const submit = document.getElementById('submit');
  const refresh = document.getElementById('refresh');
  const fields = document.getElementById('fields');
  const accepted = document.getElementById('accepted');
  let currentQuote = null, busy = false, complete = false, revision = 0;
  const money = cents => new Intl.NumberFormat('fr-FR', {style:'currency', currency:'EUR'}).format(cents / 100);
  const status = (text, error = false) => {message.textContent = text; message.classList.toggle('error', error);};
  async function api(action, payload = {}) {
    const response = await fetch('/api/cosmetics/customer', {
      method: 'POST', headers: {'Content-Type':'application/json'}, credentials:'same-origin',
      body: JSON.stringify({action, draft_id:draftId, init_data:tg?.initData || '', ...payload}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || 'Connexion interrompue. Réessayez.');
    return data;
  }
  function renderQuote(quote) {
    currentQuote = quote;
    const target = document.getElementById('lines');
    target.replaceChildren();
    for (const line of quote.lines) {
      const item = document.createElement('li');
      item.textContent = line.name + ' × ' + line.quantity + ' — ' + money(line.line_cents);
      target.append(item);
    }
    for (const [id, key] of [['subtotal','subtotal_cents'],['shipping','shipping_cents'],['total','total_cents']]) {
      document.getElementById(id).textContent = money(quote[key]);
    }
    document.getElementById('points').textContent = 'Points selon les règles NyxPepz, après validation du paiement (hors livraison).';
    submit.disabled = false;
  }
  async function updateQuote() {
    const mine = ++revision;
    currentQuote = null; submit.disabled = true; accepted.checked = false;
    try {
      const data = await api('quote', {country:form.elements.country.value});
      if (mine !== revision || complete) return;
      renderQuote(data.quote); status('Vérifiez vos coordonnées et le total.');
    } catch (error) {if (mine === revision) status(error.message, true);}
  }
  function showSuccess(reference, state) {
    complete = true; form.hidden = true; document.getElementById('success').hidden = false;
    document.getElementById('reference').textContent = reference + (state ? ' · ' + state : '');
    status('Votre commande est enregistrée.');
  }
  form.elements.country.addEventListener('change', updateQuote);
  refresh.addEventListener('click', updateQuote);
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || complete || !currentQuote || !form.reportValidity()) return;
    busy = true; submit.disabled = true; fields.disabled = true; refresh.disabled = true;
    const contact = Object.fromEntries(new FormData(form));
    // Disabled fieldsets are excluded from FormData: read the named inputs directly.
    for (const name of ['first_name','last_name','email','phone','address','address_extra','postal_code','city','country']) {
      contact[name] = form.elements[name].value.trim();
    }
    try {
      const result = await api('confirm', {contact, quote_hash:currentQuote.quote_hash, accepted:accepted.checked});
      showSuccess(result.reference);
    } catch (error) {
      status(error.message, true);
      // Re-read authoritative prices, including a concurrent price change.
      try {
        const result = await api('load');
        if (result.reference) {
          status('Commande conservée. Retournez au bot et demandez le lien de paiement.', true);
          form.hidden = true; document.getElementById('success').hidden = false;
          document.getElementById('reference').textContent = result.reference;
          complete = true;
        } else {
          renderQuote(result.quote); accepted.checked = false;
        }
      } catch {}
    } finally {
      busy = false; fields.disabled = false; refresh.disabled = false; submit.disabled = !currentQuote;
    }
  });
  document.getElementById('backBot').onclick = () => {
    if (tg?.close && tg.initData) tg.close();
    else location.assign('https://t.me/NyxPepzShopBot');
  };
  async function boot() {
    if (!draftId || !tg?.initData) {status('Ouvrez ce formulaire depuis le panier de NyxPepzShopBot.', true); return;}
    try {
      const result = await api('load');
      for (const country of result.countries) form.elements.country.add(new Option(country.name, country.code));
      for (const [name, value] of Object.entries(result.contact || {})) {
        if (form.elements[name]) form.elements[name].value = value;
      }
      if (result.reference) {
        showSuccess(result.reference, result.status);
        if (result.status === 'awaiting_payment') {
          try {await api('confirm', {accepted:true});} catch {status('Commande conservée. Demandez le lien dans le bot.', true);}
        }
        return;
      }
      form.hidden = false;
      renderQuote(result.quote);
      status('Vérifiez vos coordonnées et le total.');
    } catch (error) {status(error.message, true);}
  }
  boot();
})();
