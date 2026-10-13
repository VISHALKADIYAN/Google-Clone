document.addEventListener("DOMContentLoaded", () => {
  const themeToggle = document.getElementById("themeToggle");
  const savedTheme = localStorage.getItem("gc-theme");
  if (savedTheme === "dark") document.body.classList.add("dark");
  if (themeToggle) {
    themeToggle.textContent = document.body.classList.contains("dark") ? "☀" : "☾";
    themeToggle.addEventListener("click", () => {
      document.body.classList.toggle("dark");
      const theme = document.body.classList.contains("dark") ? "dark" : "light";
      localStorage.setItem("gc-theme", theme);
      themeToggle.textContent = theme === "dark" ? "☀" : "☾";
    });
  }

  document.querySelectorAll(".search-form").forEach(form => {
    const input = form.querySelector(".search-input");
    const clear = form.querySelector(".clear-search");
    const suggestions = form.querySelector(".suggestions");
    let requestId = 0;

    const hideSuggestions = () => {
      if (suggestions) {
        suggestions.hidden = true;
        suggestions.innerHTML = "";
      }
    };
    if (clear && input) {
      const updateClear = () => clear.style.visibility = input.value ? "visible" : "hidden";
      updateClear();
      input.addEventListener("input", () => {
        updateClear();
        if (!suggestions) return;
        const q = input.value.trim();
        const thisRequest = ++requestId;
        if (q.length < 2) { hideSuggestions(); return; }
        fetch(`/api/suggestions?q=${encodeURIComponent(q)}`)
          .then(r => r.ok ? r.json() : [])
          .then(items => {
            if (thisRequest !== requestId) return;
            suggestions.innerHTML = "";
            items.forEach(item => {
              const button = document.createElement("button");
              button.type = "button";
              button.className = "suggestion-item";
              button.textContent = item;
              button.addEventListener("click", () => {
                input.value = item;
                hideSuggestions();
                form.requestSubmit();
              });
              suggestions.appendChild(button);
            });
            suggestions.hidden = items.length === 0;
          })
          .catch(hideSuggestions);
      });
      clear.addEventListener("click", () => {
        input.value = "";
        updateClear();
        hideSuggestions();
        input.focus();
      });
      input.addEventListener("keydown", event => {
        if (event.key === "Escape") hideSuggestions();
      });
      document.addEventListener("click", event => {
        if (!form.contains(event.target)) hideSuggestions();
      });
    }

    const voice = form.querySelector(".voice-search");
    if (voice && input) {
      voice.addEventListener("click", () => {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
          alert("Voice search is not supported by this browser. Please type your search.");
          return;
        }
        const recognition = new SpeechRecognition();
        recognition.lang = "en-IN";
        recognition.interimResults = false;
        recognition.onresult = event => {
          input.value = event.results[0][0].transcript;
          form.requestSubmit();
        };
        recognition.onerror = () => alert("Voice search failed. Please try again.");
        recognition.start();
      });
    }
  });
});
