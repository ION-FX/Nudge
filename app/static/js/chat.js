(function () {
  "use strict";

  var chatEl = document.getElementById("chat");
  if (!chatEl) return;
  var chatId = chatEl.dataset.chatId;
  var csrfMeta = document.querySelector('meta[name="csrf"]');
  var csrf = csrfMeta ? csrfMeta.content : "";
  var log = document.getElementById("chat-log");
  var typing = document.getElementById("typing");
  var form = document.getElementById("chat-form");
  var input = document.getElementById("chat-text");
  var send = document.getElementById("chat-send");
  var busy = false;

  function scroll() {
    log.scrollTop = log.scrollHeight;
  }

  function addMsg(role) {
    var wrap = document.createElement("div");
    wrap.className = "msg " + role;
    var bubble = document.createElement("div");
    bubble.className = "bubble" + (role === "assistant" ? " md" : "");
    wrap.appendChild(bubble);
    log.appendChild(wrap);
    scroll();
    return bubble;
  }

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  // Minimal, always-escaped markdown: ```fences```, `inline`, **bold**.
  function fmt(text) {
    var html = esc(text);
    html = html.replace(/```([\s\S]*?)```/g, function (_m, code) {
      return "<pre class='code'>" + code.replace(/^\n/, "") + "</pre>";
    });
    html = html.replace(/`([^`\n]+)`/g, "<code>$1</code>");
    html = html.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\n/g, "<br>");
    return html;
  }

  // Re-render server-side history bubbles through the same formatter.
  Array.prototype.forEach.call(log.querySelectorAll(".bubble.md"), function (b) {
    b.innerHTML = fmt(b.textContent);
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text || busy) return;
    busy = true;
    send.disabled = true;
    addMsg("user").textContent = text;
    input.value = "";
    typing.hidden = false;
    scroll();

    var bubble = null;
    var finish = function () {
      typing.hidden = true;
      busy = false;
      send.disabled = false;
      input.focus();
      scroll();
    };

    fetch("/api/chats/" + chatId + "/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify({ content: text }),
    })
      .then(function (res) {
        if (!res.ok || !res.body) {
          return res
            .json()
            .catch(function () { return null; })
            .then(function (j) {
              throw new Error((j && j.detail) || "The tutor service is unavailable right now — please try again.");
            });
        }
        var reader = res.body.getReader();
        var dec = new TextDecoder();
        var buf = "";
        function pump() {
          return reader.read().then(function (r) {
            if (r.done) return;
            buf += dec.decode(r.value, { stream: true });
            var idx;
            while ((idx = buf.indexOf("\n\n")) >= 0) {
              var raw = buf.slice(0, idx).trim();
              buf = buf.slice(idx + 2);
              if (raw.indexOf("data:") !== 0) continue;
              var payload;
              try {
                payload = JSON.parse(raw.slice(5).trim());
              } catch (_) {
                continue;
              }
              if (payload.type === "delta") {
                if (!bubble) {
                  typing.hidden = true;
                  bubble = addMsg("assistant");
                }
                bubble.innerHTML = fmt(bubble.textContent + payload.text);
                scroll();
              } else if (payload.type === "error") {
                typing.hidden = true;
                addMsg("assistant").innerHTML = "<span class='err'>" + esc(payload.text) + "</span>";
              }
            }
            return pump();
          });
        }
        return pump();
      })
      .catch(function (err) {
        typing.hidden = true;
        addMsg("assistant").innerHTML =
          "<span class='err'>" + esc(err.message || "Connection problem — please try again.") + "</span>";
        scroll();
      })
      .finally(finish);
  });

  scroll();
})();
