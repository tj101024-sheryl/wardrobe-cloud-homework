if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/static/sw.js").catch((err) => {
      console.log("Service worker 註冊失敗：", err);
    });
  });
}
