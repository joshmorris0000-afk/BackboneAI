/*!
 * Backbone AI — Development passcode gate
 * Protects the GitHub Pages preview. Not a security boundary — development access control only.
 */
(function () {
  var KEY = 'bb_access';
  var CORRECT = '000000000';

  if (sessionStorage.getItem(KEY) === '1') return; // already unlocked this session

  // Build overlay immediately so nothing renders behind it
  var overlay = document.createElement('div');
  overlay.id = 'bb-gate';
  overlay.innerHTML = [
    '<style>',
    '#bb-gate{position:fixed;inset:0;z-index:99999;background:#05050a;display:flex;align-items:center;',
    'justify-content:center;font-family:Inter,system-ui,sans-serif;}',
    '#bb-gate-box{text-align:center;max-width:360px;padding:40px 32px;',
    'background:#0c0c14;border:1px solid #1e1e2e;border-radius:16px;}',
    '#bb-gate-logo{font-size:22px;font-weight:800;color:#fff;letter-spacing:-0.5px;margin-bottom:8px;}',
    '#bb-gate-sub{font-size:13px;color:#6b7280;margin-bottom:28px;}',
    '#bb-gate-input{width:100%;padding:12px 16px;background:#05050a;border:1px solid #2d2d3d;',
    'border-radius:8px;color:#fff;font-size:16px;letter-spacing:3px;text-align:center;',
    'outline:none;font-family:inherit;transition:border-color .2s;}',
    '#bb-gate-input:focus{border-color:#3b82f6;}',
    '#bb-gate-btn{margin-top:14px;width:100%;padding:12px;background:#3b82f6;border:none;',
    'border-radius:8px;color:#fff;font-size:15px;font-weight:600;cursor:pointer;transition:background .2s;}',
    '#bb-gate-btn:hover{background:#2563eb;}',
    '#bb-gate-err{margin-top:10px;font-size:13px;color:#f87171;min-height:18px;}',
    '</style>',
    '<div id="bb-gate-box">',
    '<div id="bb-gate-logo">Backbone AI</div>',
    '<div id="bb-gate-sub">Development preview — enter access code to continue</div>',
    '<input id="bb-gate-input" type="password" placeholder="Access code" autocomplete="off" />',
    '<button id="bb-gate-btn">Continue</button>',
    '<div id="bb-gate-err"></div>',
    '</div>'
  ].join('');

  document.documentElement.appendChild(overlay);

  function attempt() {
    var val = document.getElementById('bb-gate-input').value.trim().toUpperCase();
    if (val === CORRECT) {
      sessionStorage.setItem(KEY, '1');
      document.getElementById('bb-gate').remove();
    } else {
      var err = document.getElementById('bb-gate-err');
      err.textContent = 'Incorrect code — try again';
      document.getElementById('bb-gate-input').value = '';
      document.getElementById('bb-gate-input').focus();
      setTimeout(function () { err.textContent = ''; }, 3000);
    }
  }

  document.getElementById('bb-gate-btn').addEventListener('click', attempt);
  document.getElementById('bb-gate-input').addEventListener('keydown', function (e) {
    if (e.key === 'Enter') attempt();
  });

  // Focus input after DOM settles
  setTimeout(function () {
    var inp = document.getElementById('bb-gate-input');
    if (inp) inp.focus();
  }, 50);
})();
