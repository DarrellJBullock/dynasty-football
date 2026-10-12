// Unity → page: each message is a "dynasty-unity" event on window (Bridge.cs; the page's
// listener is frontend/src/lib/unity.ts).
mergeInto(LibraryManager.library, {
  DynastyNotify: function (type, detail) {
    window.dispatchEvent(new CustomEvent("dynasty-unity", {
      detail: { type: UTF8ToString(type), detail: UTF8ToString(detail) },
    }));
  },
});
