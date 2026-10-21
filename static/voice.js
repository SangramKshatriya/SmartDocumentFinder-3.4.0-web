(() => {
  "use strict";
  const form = document.querySelector("[data-search-form]");
  const query = document.getElementById("query");
  const mode = document.getElementById("input_mode");
  const mic = document.getElementById("voice-button");
  const status = document.getElementById("voice-status");
  const readButton = document.getElementById("read-results");

  if (mic && form && query && status && mode) {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) {
      mic.disabled = true;
      mic.title = "Voice input is not supported in this browser";
      status.textContent = "Voice input is not available in this browser. You can still type a search.";
      mic.style.opacity = ".45";
    } else {
      const recognition = new Recognition();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;
      let finalText = "";
      let submitted = false;

      mic.addEventListener("click", () => {
        if (mic.classList.contains("listening")) {
          recognition.stop();
          return;
        }
        const languageControl = document.getElementById("language");
        const selectedLanguage = languageControl && languageControl.value;
        const browserLanguage = (navigator.language || "en-IN").toLowerCase();
        recognition.lang = selectedLanguage || (browserLanguage.endsWith("-in") ? browserLanguage : window.SDF_VOICE_DEFAULT_LANGUAGE || "en-IN");
        finalText = "";
        submitted = false;
        mode.value = "voice";
        mic.classList.add("listening");
        mic.setAttribute("aria-pressed", "true");
        status.textContent = "Listening… speak the document you want to find.";
        try { recognition.start(); } catch (_error) {
          mic.classList.remove("listening");
          mic.setAttribute("aria-pressed", "false");
          status.textContent = "Voice input could not start. Try again or type your query.";
        }
      });

      recognition.onresult = (event) => {
        let interim = "";
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const phrase = event.results[i][0].transcript || "";
          if (event.results[i].isFinal) finalText += phrase;
          else interim += phrase;
        }
        query.value = (finalText || interim).trim();
        status.textContent = finalText ? `Heard: “${finalText.trim()}”. Searching…` : `Hearing: ${interim}`;
        if (finalText.trim() && !submitted) {
          submitted = true;
          mode.value = "voice";
          window.setTimeout(() => form.requestSubmit(), 250);
        }
      };
      recognition.onerror = (event) => {
        mic.classList.remove("listening");
        mic.setAttribute("aria-pressed", "false");
        const messages = {
          "not-allowed": "Microphone permission was denied. Allow microphone access in your browser settings.",
          "no-speech": "No speech was detected. Select the microphone and try again.",
          "network": "Browser speech recognition needs a network connection. You can type your query instead.",
        };
        status.textContent = messages[event.error] || `Voice input stopped (${event.error}). You can type your query instead.`;
      };
      recognition.onend = () => {
        mic.classList.remove("listening");
        mic.setAttribute("aria-pressed", "false");
        if (!submitted && !finalText.trim() && status.textContent.startsWith("Listening")) {
          status.textContent = "Voice input stopped. Tap the microphone to try again.";
        }
      };
    }
  }

  if (readButton) {
    const resultArea = document.getElementById("search-results");
    if (!resultArea || !resultArea.dataset.speechResults.trim()) readButton.hidden = true;
    readButton.addEventListener("click", () => {
      if (!("speechSynthesis" in window)) {
        readButton.textContent = "Audio is not supported";
        return;
      }
      const text = (resultArea && resultArea.dataset.speechResults || "").trim();
      if (!text) return;
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text.slice(0, 2500));
      utterance.lang = (document.getElementById("language")?.value || "en-IN");
      window.speechSynthesis.speak(utterance);
    });
  }
})();
