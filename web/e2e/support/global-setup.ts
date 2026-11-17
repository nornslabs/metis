import { seedUser } from "./session";

export default function globalSetup(): void {
  seedUser();
}
