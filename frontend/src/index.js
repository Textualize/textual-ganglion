import "./styles.scss";

import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebglAddon } from "@xterm/addon-webgl";
import { CanvasAddon } from "@xterm/addon-canvas";
import { Unicode11Addon } from "@xterm/addon-unicode11";
import { WebLinksAddon } from "@xterm/addon-web-links";
import { ClipboardAddon } from "@xterm/addon-clipboard";

class TextualTerminal {
  constructor(element, options) {
    this.element = element;
    this.ping = options.ping;
    this.websocket_url = element.dataset.sessionWebsocketUrl;
    this.instance = undefined;
    const font_size = element.dataset.fontSize;
    this.terminal = new Terminal({
      allowProposedApi: true,
      fontSize: font_size,
      scrollback: 0,
      // disableLigatures: true,
      // customGlyphs: true,
      fontFamily: "'Roboto Mono', Monaco, 'Courier New', monospace",
    });

    this.fitAddon = new FitAddon();
    this.terminal.loadAddon(this.fitAddon);
    this.webglAddon = new WebglAddon();
    this.terminal.loadAddon(this.webglAddon);
    this.canvasAddon = new CanvasAddon();
    this.terminal.loadAddon(this.canvasAddon);
    this.unicode11Addon = new Unicode11Addon();
    this.terminal.loadAddon(this.unicode11Addon);
    this.weblinksAddon = new WebLinksAddon();
    this.terminal.loadAddon(this.weblinksAddon);
    this.terminal.unicode.activeVersion = "11";
    const clipboardAddon = new ClipboardAddon();
    this.terminal.loadAddon(clipboardAddon);
    this.terminal.open(element);

    this.socket = null;

    this.bufferedBytes = 0;
    this.refreshBytes = 0;
    this.size = null;

    this.terminal.element.querySelector(".xterm-screen").addEventListener(
      "blur",
      (event) => {
        this.onBlur();
      },
      true
    );

    this.terminal.element.querySelector(".xterm-screen").addEventListener(
      "focus",
      (event) => {
        this.onFocus();
      },
      true
    );

    this.terminal.onResize((event) => {
      this.size = { width: event.cols, height: event.rows };
      this.sendSize();
    });

    this.terminal.onData((data) => {
      this.socket.send(JSON.stringify(["stdin", data]));
    });

    window.onresize = () => {
      this.fit();
    };
  }

  sendSize() {
    if (this.size) {
      const meta = JSON.stringify(["resize", this.size]);
      if (this.socket) {
        this.socket.send(meta);
      }
    }
  }

  sendPing() {
    const epoch_milliseconds = new Date().getTime();
    const meta = JSON.stringify(["ping", "" + epoch_milliseconds]);
    if (this.socket) {
      this.socket.send(meta);
    }
  }

  onPong(pong_data) {
    const epoch_milliseconds = new Date().getTime();
    const delta = epoch_milliseconds - parseInt(pong_data);
    console.log("ping=" + delta + "ms");
  }

  onFocus() {
    const meta = JSON.stringify(["focus"]);
    if (this.socket) {
      this.socket.send(meta);
    }
  }

  onBlur() {
    const meta = JSON.stringify(["blur"]);
    if (this.socket) {
      this.socket.send(meta);
    }
  }

  fit() {
    this.fitAddon.fit(this.element);
  }

  async connect() {
    if (this.ping) {
      await fetch(this.ping, {
        method: "GET",
        mode: "no-cors",
      });
    }

    this.fit();
    const initial_size = this.fitAddon.proposeDimensions();
    this.socket = new WebSocket(
      this.websocket_url +
        "?width=" +
        initial_size.cols +
        "&height=" +
        initial_size.rows
    );
    this.socket.binaryType = "arraybuffer";

    // Connection opened
    this.socket.addEventListener("open", (event) => {
      this.element.classList.add("-connected");
      this.fit();
      this.sendSize();

      setTimeout(() => {
        this.sendPing();
      }, 3);

      document.querySelector("body").classList.add("-loaded");
    });

    this.socket.addEventListener("close", (event) => {
      console.log("CLOSED");
      document.querySelector("body").classList.add("-closed");
    });

    // Listen for messages
    this.socket.addEventListener("message", (event) => {
      if (typeof event.data === "string") {
        // String messages are encoded as JSON
        const packetData = JSON.parse(event.data);
        const packetType = packetData[0];
        const packetPayload = packetData[1];
        switch (packetType) {
          case "log":
            console.log("LOG", packetPayload);
            break;
          case "pong":
            this.onPong(packetPayload);
            break;
          case "instance_id":
            this.instance = packetPayload;
            break;
          case "open_url":
            const url = packetPayload.url;
            const new_tab = packetPayload.new_tab;
            window.open(url, new_tab ? "_blank" : "_self");
            break;
          case "deliver_file_start":
            const deliveryKey = packetPayload;
            const instanceParam = this.instance
              ? `?instance=${this.instance}`
              : "";
            const downloadUrl = `${window.location.origin}/download/${deliveryKey}${instanceParam}`;
            window.open(downloadUrl, "_blank");
            break;
        }
      } else {
        /* Binary messages are stdout data. */
        const bytearray = new Uint8Array(event.data);
        this.bufferedBytes += bytearray.length;
        this.refreshBytes += bytearray.length;
        this.terminal.write(bytearray, () => {
          this.bufferedBytes -= bytearray.length;
        });

        if (bytearray.length > 10) {
          document.querySelector("body").classList.add("-first-byte");
        }
      }
    });
  }
}

window.onload = (event) => {
  const terminals = document.querySelectorAll(".textual-terminal");
  const urlParams = new URLSearchParams(window.location.search);
  const delay = urlParams.get("delay");
  const ping = urlParams.get("ping");

  if (delay) {
    document.querySelector("#start").classList.add("-delay");
  }
  terminals.forEach((terminal_element) => {
    const textual_terminal = new TextualTerminal(terminal_element, {
      ping: ping,
    });
    textual_terminal.fit();

    if (!delay) {
      textual_terminal.connect();
    }
  });
};
