/* OracleAI frontend runtime boundary.
 *
 * Vanilla JS keeps a small public `window.app` facade for the current screens,
 * but the mutable state itself lives in one explicit object. New modules should
 * read/write `app.state` and expose behaviour through `app.*` only at the edge.
 */
(function (root) {
  'use strict';

  function createState() {
    return {
      me: null,
      agents: [],
      today: null,
      spreads: null,
      moonWeek: null,
      dailyPulse: null,
      view: 'home',
      chat: {
        key: null,
        spec: null,
        messages: [],
        pending: null,
        busy: false,
        request: null,
        tid: null,
        sessions: [],
        draft: ''
      }
    };
  }

  function bindLegacyState(app, state) {
    [
      'me', 'agents', 'today', 'spreads', 'moonWeek', 'dailyPulse',
      'view', 'chat'
    ].forEach(function (key) {
      Object.defineProperty(app, key, {
        configurable: true,
        enumerable: true,
        get: function () { return state[key]; },
        set: function (value) { state[key] = value; }
      });
    });
  }

  root.OracleRuntime = Object.freeze({ createState, bindLegacyState });
}(window));
