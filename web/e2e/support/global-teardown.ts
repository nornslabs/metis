import { removeUser } from "./session";

export default function globalTeardown(): void {
  removeUser();
}
