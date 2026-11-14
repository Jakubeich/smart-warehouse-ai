import { errorText } from "@/lib/i18n";
import { useEffect } from "react";
import { messageSchema } from "@/types/domain";
import { useSimulation } from "@/stores/simulation";
export function useLive() {
  const id = useSimulation((s) => s.simulation?.id);
  useEffect(() => {
    if (!id) return;
    let stopped = false;
    let socket: WebSocket;
    let timer: ReturnType<typeof setTimeout>;
    let attempt = 0;
    const isCurrent = () =>
      !stopped && useSimulation.getState().simulation?.id === id;
    function connect() {
      if (!isCurrent()) return;
      useSimulation.getState().setConnection("connecting");
      socket = new WebSocket(
        `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/simulations/${id}`,
      );
      socket.onopen = () => {
        if (!isCurrent()) return;
        attempt = 0;
        useSimulation.getState().setConnection("connected");
      };
      socket.onmessage = (event: MessageEvent<string>) => {
        if (!isCurrent()) return;
        try {
          const parsed = messageSchema.parse(JSON.parse(event.data));
          if (
            parsed.state.id === id &&
            parsed.sequence === parsed.state.sequence
          )
            useSimulation.getState().setSimulation(parsed.state);
        } catch (error) {
          useSimulation
            .getState()
            .setError(`Neplatná aktualizace simulace: ${errorText(error)}`);
        }
      };
      socket.onclose = (event) => {
        if (!isCurrent()) return;
        useSimulation.getState().setConnection("disconnected");
        if (event.code === 4404) {
          useSimulation.getState().clear();
          useSimulation
            .getState()
            .setError("Tato simulace již není dostupná. Vytvořte nový běh.");
          return;
        }
        timer = setTimeout(connect, Math.min(1000 * 2 ** attempt++, 10000));
      };
      socket.onerror = () => socket.close();
    }
    connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      socket.close();
    };
  }, [id]);
}
